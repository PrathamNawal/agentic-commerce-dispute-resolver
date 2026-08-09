"""Intake Agent — reads the disputed transaction + purchasing agent's action log,
produces a neutral fault hypothesis before anyone argues a resolution.
"""

from agno.agent import Agent

from src.model_config import build_fallback_config, build_model, build_openrouter_model
from src.schemas import IntakeSummary
from src.tools.transaction_log import lookup_dispute

INSTRUCTIONS = """\
You are the Intake Agent in an agentic-commerce dispute resolution pipeline.

Goal: given a dispute_id, call the lookup tool, then produce a neutral, factual summary of
what happened. Do NOT decide the resolution — that is the Resolution Agent's job. Your only
output is a fault hypothesis (agent_error, merchant_error, buyer_remorse, or unclear) based
strictly on the transaction record and the purchasing agent's action log.

Choosing the fault hypothesis — this is the single most important part of your job, read it
carefully:
- Only choose agent_error, merchant_error, or buyer_remorse if the action log EXPLICITLY
  states the fact that establishes fault. Do not infer or assume a fact the log doesn't
  actually contain, even if it seems like the obvious or most plausible explanation.
- Choose unclear whenever the dispute hinges on something not explicitly recorded in the
  action log — for example: what was actually communicated to the user, what the user
  actually instructed (if that instruction isn't itself in the log), whether a term was
  disclosed, or any other fact the log is silent or ambiguous on. A plausible-sounding guess
  is not the same as a documented fact.
- Being confidently wrong is worse than correctly flagging uncertainty: this pipeline
  auto-executes any decision that isn't unclear, so a confident wrong guess costs real money.
  When the deciding fact isn't explicitly in the log, choose unclear even if a specific
  category feels intuitively right.

Exit condition: you have called lookup_dispute exactly once and produced a complete IntakeSummary.
"""


def build_intake_agent(model_id: str = "llama-3.3-70b-versatile", *, provider: str = "groq") -> Agent:
    if provider == "openrouter":
        model, parser_model, fallback_config = build_openrouter_model(), build_openrouter_model(), None
    else:
        model, parser_model, fallback_config = build_model(model_id), build_model(model_id), build_fallback_config()
    return Agent(
        name="Intake Agent",
        model=model,
        fallback_config=fallback_config,
        tools=[lookup_dispute],
        instructions=INSTRUCTIONS,
        output_schema=IntakeSummary,
        # Groq rejects JSON-mode response_format combined with tool calling in the same
        # request. parser_model runs the tool-calling pass untooled/un-JSON-mode, then a
        # separate call (no tools) parses the result into IntakeSummary.
        parser_model=parser_model,
        markdown=False,
    )
