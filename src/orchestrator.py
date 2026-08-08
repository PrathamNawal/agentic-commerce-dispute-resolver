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
`.content`. _run_stage catches that by type-checking, and rebuilds the whole agent on
OpenRouter as an explicit second attempt.
"""

from dataclasses import dataclass
from typing import Callable, Iterator, Tuple, Type, TypeVar

from agno.agent import Agent

from src.agents.intake import build_intake_agent
from src.agents.policy import build_policy_agent
from src.agents.resolution import build_resolution_agent
from src.agents.reviewer import build_reviewer_agent
from src.model_config import openrouter_available
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
    """Runs one agent stage; if the primary (Groq) call didn't produce the expected schema —
    whether because it raised or because it silently returned bad content — rebuilds the same
    agent on OpenRouter and retries once, if a key is configured."""
    result = build_agent(provider="groq").run(prompt)
    if isinstance(result.content, schema_type):
        return result.content

    if not openrouter_available():
        raise RuntimeError(
            f"{schema_type.__name__} stage failed and no OPENROUTER_API_KEY is set to fall "
            f"back to: {result.content!r}"
        )

    fallback_result = build_agent(provider="openrouter").run(prompt)
    if isinstance(fallback_result.content, schema_type):
        return fallback_result.content

    raise RuntimeError(
        f"{schema_type.__name__} stage failed on both Groq and the OpenRouter fallback: "
        f"{fallback_result.content!r}"
    )


def resolve_dispute_stream(
    dispute_id: str, model_id: str = "llama-3.3-70b-versatile"
) -> Iterator[Tuple[str, object]]:
    """Yields ("intake", IntakeSummary), ("policy", PolicyFinding), ("resolution", Resolution),
    ("review", ReviewScore), then ("done", PipelineResult) as each stage completes."""

    intake: IntakeSummary = _run_stage(
        lambda provider: build_intake_agent(model_id, provider=provider),
        f"Process dispute_id: {dispute_id}",
        IntakeSummary,
    )
    yield "intake", intake

    policy: PolicyFinding = _run_stage(
        lambda provider: build_policy_agent(model_id, provider=provider),
        f"Intake fault hypothesis: {intake.fault_hypothesis}\n"
        f"Intake summary: {intake.summary}\n"
        f"Key facts: {intake.key_facts}",
        PolicyFinding,
    )
    yield "policy", policy

    resolution: Resolution = _run_stage(
        lambda provider: build_resolution_agent(model_id, provider=provider),
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
        lambda provider: build_reviewer_agent(model_id, provider=provider),
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
def resolve_dispute(dispute_id: str, model_id: str = "llama-3.3-70b-versatile") -> PipelineResult:
    result: PipelineResult | None = None
    for stage, payload in resolve_dispute_stream(dispute_id, model_id):
        if stage == "done":
            result = payload
    assert result is not None
    return result
