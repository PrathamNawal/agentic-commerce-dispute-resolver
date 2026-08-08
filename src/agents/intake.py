"""Intake Agent — reads the disputed transaction + purchasing agent's action log,
produces a neutral fault hypothesis before anyone argues a resolution.
"""

from agno.agent import Agent
from agno.models.groq import Groq

from src.schemas import IntakeSummary
from src.tools.transaction_log import lookup_dispute

INSTRUCTIONS = """\
You are the Intake Agent in an agentic-commerce dispute resolution pipeline.

Goal: given a dispute_id, call the lookup tool, then produce a neutral, factual summary of
what happened. Do NOT decide the resolution — that is the Resolution Agent's job. Your only
output is a fault hypothesis (agent_error, merchant_error, buyer_remorse, or unclear) based
strictly on the transaction record and the purchasing agent's action log.

Exit condition: you have called lookup_dispute exactly once and produced a complete IntakeSummary.
"""


def build_intake_agent(model_id: str = "llama-3.3-70b-versatile") -> Agent:
    return Agent(
        name="Intake Agent",
        model=Groq(id=model_id, temperature=0.15, max_tokens=1024, timeout=20),
        tools=[lookup_dispute],
        instructions=INSTRUCTIONS,
        output_schema=IntakeSummary,
        markdown=False,
    )
