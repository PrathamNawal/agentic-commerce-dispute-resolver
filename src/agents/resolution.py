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
input), decide: refund, replace, escalate, or deny. Your rationale must explicitly reference
the policy finding and at least one fact from the intake summary. Draft a short, professional
buyer-facing message explaining the decision in plain language.

Guardrail: if the policy finding's confidence is "low", or the dispute amount exceeds $200,
you must choose "escalate" rather than deciding unilaterally — do not override this rule.

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
