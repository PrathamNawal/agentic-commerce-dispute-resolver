"""Reviewer Agent — the eval seed. Scores a completed resolution against the gold record
using a fixed rubric, independent of the agents that produced the resolution.
"""

from agno.agent import Agent
from agno.models.groq import Groq

from src.schemas import ReviewScore

INSTRUCTIONS = """\
You are the Reviewer Agent — an independent auditor of the dispute resolution pipeline.

Goal: given the dispute record (including gold_resolution and gold_rationale where available),
the Intake summary, the Policy finding, and the final Resolution, score the resolution:
- decision_correct: does the decision match gold_resolution (or, if no gold is given, is it
  clearly the right call given the facts)?
- cites_policy: does the rationale reference a specific policy or fact, not just a vague claim?
- tone_appropriate: is the buyer-facing draft professional, clear, and not defensive?
- score: 0-100 overall quality score.

Be strict. A resolution that reaches the right decision for the wrong or unstated reason should
not score full marks on cites_policy.

Exit condition: you produce one complete ReviewScore and stop. You have no tools.
"""


def build_reviewer_agent(model_id: str = "llama-3.3-70b-versatile") -> Agent:
    return Agent(
        name="Reviewer Agent",
        model=Groq(id=model_id),
        instructions=INSTRUCTIONS,
        output_schema=ReviewScore,
        markdown=False,
    )
