"""Policy Agent — retrieves the platform's own agentic-commerce dispute policy (and,
where useful, real-world merchant/ACP policy language) applicable to the intake's fault hypothesis.
"""

from agno.agent import Agent
from agno.models.groq import Groq

from src.schemas import PolicyFinding
from src.tools.policy_search import get_platform_policy, search_merchant_policy

INSTRUCTIONS = """\
You are the Policy Agent in an agentic-commerce dispute resolution pipeline.

Goal: given the Intake Agent's fault hypothesis and summary, call get_platform_policy with the
closest matching fault category (agent_error, merchant_error, disclosure_failure, buyer_remorse)
to retrieve the platform's own rule. If the case is ambiguous or you need real-world grounding,
also call search_merchant_policy with a targeted query.

Exit condition: you have retrieved at least the platform policy and produced a PolicyFinding
that states which resolution the policy supports and how confident you are.
"""


def build_policy_agent(model_id: str = "llama-3.3-70b-versatile") -> Agent:
    return Agent(
        name="Policy Agent",
        model=Groq(id=model_id, temperature=0.15, max_tokens=1024, timeout=20),
        tools=[get_platform_policy, search_merchant_policy],
        instructions=INSTRUCTIONS,
        output_schema=PolicyFinding,
        markdown=False,
    )
