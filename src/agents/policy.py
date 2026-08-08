"""Policy Agent — retrieves the platform's own agentic-commerce dispute policy (and,
where useful, real-world merchant/ACP policy language) applicable to the intake's fault hypothesis.
"""

from agno.agent import Agent

from src.model_config import build_fallback_config, build_model, build_openrouter_model
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


def build_policy_agent(model_id: str = "llama-3.3-70b-versatile", *, provider: str = "groq") -> Agent:
    if provider == "openrouter":
        model, parser_model, fallback_config = build_openrouter_model(), build_openrouter_model(), None
    else:
        model, parser_model, fallback_config = build_model(model_id), build_model(model_id), build_fallback_config()
    return Agent(
        name="Policy Agent",
        model=model,
        fallback_config=fallback_config,
        tools=[get_platform_policy, search_merchant_policy],
        instructions=INSTRUCTIONS,
        output_schema=PolicyFinding,
        # See intake.py — Groq can't combine JSON-mode structured output with tool calling
        # in one request; parser_model does the schema parse as a separate untooled call.
        parser_model=parser_model,
        markdown=False,
    )
