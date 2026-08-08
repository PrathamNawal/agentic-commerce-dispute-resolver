"""Shared structured-output schemas passed between agents in the dispute pipeline."""

from typing import Literal

from pydantic import BaseModel, Field


class IntakeSummary(BaseModel):
    dispute_id: str
    fault_hypothesis: Literal["agent_error", "merchant_error", "buyer_remorse", "unclear"]
    summary: str = Field(description="Neutral one-paragraph summary of what happened and why it's disputed")
    key_facts: list[str] = Field(description="Bullet facts pulled from the transaction and agent action log")


class PolicyFinding(BaseModel):
    applicable_policy: str = Field(description="The specific policy clause or precedent that applies")
    policy_source: str = Field(description="Where this came from: doc title/URL or 'no policy found'")
    supports_resolution: Literal["refund", "replace", "escalate", "deny"]
    confidence: Literal["high", "medium", "low"]


class Resolution(BaseModel):
    decision: Literal["refund", "replace", "deny"] = Field(
        description="The agent's substantive suggested action — always filled in, even when requires_human_review is True"
    )
    requires_human_review: bool = Field(
        description="True if policy confidence is low or the amount exceeds the guardrail threshold; decision is then a suggestion for the reviewer, not an auto-executed action"
    )
    escalation_reason: str | None = Field(
        default=None, description="Why human review is required, set only when requires_human_review is True"
    )
    amount_usd: float | None = Field(default=None, description="Refund/credit amount if applicable")
    rationale: str = Field(description="Why this decision, citing the policy finding and intake facts")
    buyer_response_draft: str = Field(description="Customer-facing message explaining the decision")


class ReviewScore(BaseModel):
    decision_correct: bool = Field(description="Does the decision match what the gold/policy record implies?")
    cites_policy: bool = Field(description="Does the rationale reference a specific policy or fact?")
    tone_appropriate: bool = Field(description="Is the buyer-facing draft professional and clear?")
    score: int = Field(ge=0, le=100)
    notes: str
