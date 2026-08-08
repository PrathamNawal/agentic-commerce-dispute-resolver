"""Resolution Agent — takes the intake summary + policy finding and commits to a decision
plus a buyer-facing draft response. No tools: this agent reasons over what the prior two
agents already gathered, it does not go fetch new facts.
"""

from agno.agent import Agent
from agno.models.groq import Groq

from src.schemas import Resolution

INSTRUCTIONS = """\
You are the Resolution Agent in an agentic-commerce dispute resolution pipeline.

Goal: given the Intake Agent's summary and the Policy Agent's finding (both provided in your
input), decide your best-judgment action: refund, replace, or deny. Always fill in a
substantive decision — never leave it blank or generic, even if the case will need human
review. Your rationale must explicitly reference the policy finding and at least one fact
from the intake summary. Draft a short, professional buyer-facing message explaining the
decision in plain language.

Guardrail — set requires_human_review=true and state why in escalation_reason if ANY of these
hold (do not override this rule):
1. the policy finding's confidence is "low"
2. the dispute amount exceeds $200
3. the intake fault_hypothesis is "unclear" — an unclear fault means the facts themselves are
   contested (e.g. conflicting accounts of what instruction was given), which no policy lookup
   can resolve, regardless of dollar amount
This does NOT change what decision/amount/rationale you produce: still give your best
suggested call, since a human reviewer needs something concrete to approve or override, not
an empty flag.

Exit condition: you produce one complete Resolution and stop.
"""


def build_resolution_agent(model_id: str = "llama-3.3-70b-versatile") -> Agent:
    return Agent(
        name="Resolution Agent",
        model=Groq(id=model_id, temperature=0.15, max_tokens=1024, timeout=20),
        instructions=INSTRUCTIONS,
        output_schema=Resolution,
        markdown=False,
    )
