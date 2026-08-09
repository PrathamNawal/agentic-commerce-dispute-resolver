"""Chains Intake -> Policy -> Resolution -> Reviewer for a single dispute.

This is a deliberately simple sequential pipeline, not a generalized router — Agno's own
agent-to-agent handoff machinery would be overkill for a fixed 4-stage flow. If a future
dispute type needed conditional branching (e.g. skip Reviewer in production), that's the
seam where a real Agno Team/Workflow would replace this function.

resolve_dispute_stream() yields each stage's output as it completes, so a UI (Streamlit) can
render the pipeline running live instead of waiting for the final result. resolve_dispute()
is the same logic, just collapsed to the final PipelineResult for callers that don't need the
intermediate steps (CLI, eval harness).

Each stage is run via _run_stage(), which explicitly checks whether the returned content is
the expected schema type — not just whether the call raised. Agno's built-in fallback_config
covers the primary `model` on a rate-limit error, but a Groq failure inside `parser_model`
(used by Intake/Policy to work around the JSON-mode + tool-calling conflict, see
src/agents/intake.py) doesn't raise at all — it silently returns an error string as
`.content`. _run_stage catches that by type-checking, and walks
model_config.FALLBACK_PROVIDER_ORDER (groq -> openrouter -> cerebras) rebuilding the whole
agent on each until one produces the right schema, or the chain is exhausted.
"""

from dataclasses import dataclass
from typing import Callable, Iterator, Tuple, Type, TypeVar

from agno.agent import Agent

from src.agents.intake import build_intake_agent
from src.agents.policy import build_policy_agent
from src.agents.resolution import build_resolution_agent
from src.agents.reviewer import build_reviewer_agent
from src.exceptions import CapacityExhaustedError, PipelineStageError, looks_like_capacity_issue
from src.model_config import FALLBACK_PROVIDER_ORDER, available_fallback_providers
from src.observability import traced
from src.schemas import IntakeSummary, PolicyFinding, ReviewScore, Resolution
from src.tools.escalation_queue import queue_for_review
from src.tools.transaction_log import lookup_dispute_with_gold

T = TypeVar("T")


@dataclass
class PipelineResult:
    dispute_id: str
    intake: IntakeSummary
    policy: PolicyFinding
    resolution: Resolution
    review: ReviewScore


def _run_stage(build_agent: Callable[..., Agent], prompt: str, schema_type: Type[T]) -> T:
    """Runs one agent stage, walking FALLBACK_PROVIDER_ORDER (groq -> openrouter -> gemini,
    skipping any provider without a key configured) until one produces the expected schema —
    whichever provider that content check fails on, whether by raising or by silently
    returning bad content.

    Raises CapacityExhaustedError (not a bare RuntimeError) when every failure looks like a
    rate-limit/quota condition — the UI treats that very differently from an actual bug, see
    src/exceptions.py."""
    providers_to_try = ["groq"] + available_fallback_providers()
    attempts: list[tuple[str, object]] = []

    for provider in providers_to_try:
        result = build_agent(provider=provider).run(prompt)
        if isinstance(result.content, schema_type):
            return result.content
        attempts.append((provider, result.content))

    tried = ", ".join(providers_to_try)
    details = "\n".join(f"  {p}: {c!r}" for p, c in attempts)
    message = (
        f"{schema_type.__name__} stage failed on every available provider ({tried}).\n{details}\n"
        f"Configure another key from {FALLBACK_PROVIDER_ORDER[1:]} to extend the fallback chain."
    )
    exc_cls = CapacityExhaustedError if looks_like_capacity_issue(*(c for _, c in attempts)) else PipelineStageError
    raise exc_cls(message)


def resolve_dispute_stream(
    dispute_id: str, model_id: str = "llama-3.3-70b-versatile", use_cache: bool = True
) -> Iterator[Tuple[str, object]]:
    """Yields ("intake", IntakeSummary), ("policy", PolicyFinding), ("resolution", Resolution),
    ("review", ReviewScore), then ("done", PipelineResult) as each stage completes.

    use_cache=False forces a live call on every stage — needed for eval runs where a cached
    result from an earlier run would defeat the point (e.g. the before/after prompt
    comparison, which must measure the current prompt against a live model, not a cached
    response from before the prompt changed)."""

    intake: IntakeSummary = _run_stage(
        lambda provider: build_intake_agent(model_id, provider=provider, use_cache=use_cache),
        f"Process dispute_id: {dispute_id}",
        IntakeSummary,
    )
    yield "intake", intake

    policy: PolicyFinding = _run_stage(
        lambda provider: build_policy_agent(model_id, provider=provider, use_cache=use_cache),
        f"Intake fault hypothesis: {intake.fault_hypothesis}\n"
        f"Intake summary: {intake.summary}\n"
        f"Key facts: {intake.key_facts}",
        PolicyFinding,
    )
    yield "policy", policy

    resolution: Resolution = _run_stage(
        lambda provider: build_resolution_agent(model_id, provider=provider, use_cache=use_cache),
        f"Intake fault hypothesis: {intake.fault_hypothesis}\n"
        f"Intake summary: {intake.summary}\n"
        f"Key facts: {intake.key_facts}\n"
        f"Policy finding: {policy.applicable_policy} (source: {policy.policy_source})\n"
        f"Policy supports: {policy.supports_resolution} (confidence: {policy.confidence})",
        Resolution,
    )

    if resolution.requires_human_review:
        queue_for_review(
            dispute_id=dispute_id,
            suggested_decision=resolution.decision,
            suggested_amount_usd=resolution.amount_usd,
            suggested_rationale=resolution.rationale,
            escalation_reason=resolution.escalation_reason or "no reason given",
        )
    yield "resolution", resolution

    dispute_record = lookup_dispute_with_gold(dispute_id)
    review: ReviewScore = _run_stage(
        lambda provider: build_reviewer_agent(model_id, provider=provider, use_cache=use_cache),
        f"Dispute record: {dispute_record}\n"
        f"Intake: {intake.model_dump()}\n"
        f"Policy finding: {policy.model_dump()}\n"
        f"Resolution: {resolution.model_dump()}",
        ReviewScore,
    )
    yield "review", review

    yield "done", PipelineResult(
        dispute_id=dispute_id,
        intake=intake,
        policy=policy,
        resolution=resolution,
        review=review,
    )


@traced(name="dispute_pipeline")
def resolve_dispute(dispute_id: str, model_id: str = "llama-3.3-70b-versatile", use_cache: bool = True) -> PipelineResult:
    result: PipelineResult | None = None
    for stage, payload in resolve_dispute_stream(dispute_id, model_id, use_cache=use_cache):
        if stage == "done":
            result = payload
    assert result is not None
    return result
