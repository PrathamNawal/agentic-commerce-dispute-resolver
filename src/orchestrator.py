"""Chains Intake -> Policy -> Resolution -> Reviewer for a single dispute.

This is a deliberately simple sequential pipeline, not a generalized router — Agno's own
agent-to-agent handoff machinery would be overkill for a fixed 4-stage flow. If a future
dispute type needed conditional branching (e.g. skip Reviewer in production), that's the
seam where a real Agno Team/Workflow would replace this function.

resolve_dispute_stream() yields each stage's output as it completes, so a UI (Streamlit) can
render the pipeline running live instead of waiting for the final result. resolve_dispute()
is the same logic, just collapsed to the final PipelineResult for callers that don't need the
intermediate steps (CLI, eval harness).
"""

from dataclasses import dataclass
from typing import Iterator, Tuple

from src.agents.intake import build_intake_agent
from src.agents.policy import build_policy_agent
from src.agents.resolution import build_resolution_agent
from src.agents.reviewer import build_reviewer_agent
from src.observability import traced
from src.schemas import IntakeSummary, PolicyFinding, ReviewScore, Resolution
from src.tools.escalation_queue import queue_for_review
from src.tools.transaction_log import lookup_dispute


@dataclass
class PipelineResult:
    dispute_id: str
    intake: IntakeSummary
    policy: PolicyFinding
    resolution: Resolution
    review: ReviewScore


def resolve_dispute_stream(
    dispute_id: str, model_id: str = "llama-3.3-70b-versatile"
) -> Iterator[Tuple[str, object]]:
    """Yields ("intake", IntakeSummary), ("policy", PolicyFinding), ("resolution", Resolution),
    ("review", ReviewScore), then ("done", PipelineResult) as each stage completes."""
    intake_agent = build_intake_agent(model_id)
    policy_agent = build_policy_agent(model_id)
    resolution_agent = build_resolution_agent(model_id)
    reviewer_agent = build_reviewer_agent(model_id)

    intake_run = intake_agent.run(f"Process dispute_id: {dispute_id}")
    intake: IntakeSummary = intake_run.content
    yield "intake", intake

    policy_run = policy_agent.run(
        f"Intake fault hypothesis: {intake.fault_hypothesis}\n"
        f"Intake summary: {intake.summary}\n"
        f"Key facts: {intake.key_facts}"
    )
    policy: PolicyFinding = policy_run.content
    yield "policy", policy

    resolution_run = resolution_agent.run(
        f"Intake fault hypothesis: {intake.fault_hypothesis}\n"
        f"Intake summary: {intake.summary}\n"
        f"Key facts: {intake.key_facts}\n"
        f"Policy finding: {policy.applicable_policy} (source: {policy.policy_source})\n"
        f"Policy supports: {policy.supports_resolution} (confidence: {policy.confidence})"
    )
    resolution: Resolution = resolution_run.content

    if resolution.requires_human_review:
        queue_for_review(
            dispute_id=dispute_id,
            suggested_decision=resolution.decision,
            suggested_amount_usd=resolution.amount_usd,
            suggested_rationale=resolution.rationale,
            escalation_reason=resolution.escalation_reason or "no reason given",
        )
    yield "resolution", resolution

    dispute_record = lookup_dispute(dispute_id)
    review_run = reviewer_agent.run(
        f"Dispute record: {dispute_record}\n"
        f"Intake: {intake.model_dump()}\n"
        f"Policy finding: {policy.model_dump()}\n"
        f"Resolution: {resolution.model_dump()}"
    )
    review: ReviewScore = review_run.content
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
