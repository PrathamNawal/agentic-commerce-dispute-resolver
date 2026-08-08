"""Shared model construction: Groq primary, OpenRouter fallback on rate limits.

Two fallback layers exist, because Agno's own fallback_config only covers an agent's primary
`model` — it does NOT cover `parser_model`, and Agno doesn't raise a catchable exception when
a Groq call fails inside parser_model; it silently returns an error string as `.content`
instead of the parsed schema. That means neither "wrap it in try/except" nor "just set
fallback_config" is sufficient on its own:

1. build_fallback_config() — Agno's built-in mechanism, wraps the primary `model`. Handles
   Resolution/Reviewer (no parser_model) and the tool-calling half of Intake/Policy.
2. build_openrouter_model() — used by orchestrator.py's explicit retry: after each stage, it
   checks whether `.content` is actually the expected schema type (not just "did it raise"),
   and if not, rebuilds that one agent entirely on OpenRouter (both model and parser_model)
   and retries. This is what actually covers the parser_model gap.

Both are no-ops without OPENROUTER_API_KEY set — behavior is unchanged from plain Groq for
anyone who hasn't set up OpenRouter.

OpenRouter's free-tier model lineup and reliability both rotate over time — confirmed
firsthand while building this: "meta-llama/llama-3.3-70b-instruct:free" had been pulled from
the free tier entirely (404), and "openai/gpt-oss-20b:free" was hitting transient backend
timeouts on OpenRouter's side. "nvidia/nemotron-3-super-120b-a12b:free" is the one actually
verified end-to-end (full 4-stage pipeline, correct decision, 95/100 reviewer score) as of
this writing. If OPENROUTER_FALLBACK_MODEL stops working, check
https://openrouter.ai/models?max_price=0 for a current free model id and override the env
var rather than editing the default here.
"""

import os
from typing import Optional

from agno.models.fallback import FallbackConfig
from agno.models.groq import Groq
from agno.models.openrouter import OpenRouter

DEFAULT_OPENROUTER_FALLBACK_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"


def build_model(
    model_id: str = "llama-3.3-70b-versatile",
    *,
    temperature: float = 0.15,
    max_tokens: int = 1024,
    timeout: int = 20,
) -> Groq:
    return Groq(id=model_id, temperature=temperature, max_tokens=max_tokens, timeout=timeout)


def build_openrouter_model(*, temperature: float = 0.15, max_tokens: int = 1024) -> OpenRouter:
    fallback_model_id = os.getenv("OPENROUTER_FALLBACK_MODEL", DEFAULT_OPENROUTER_FALLBACK_MODEL)
    return OpenRouter(id=fallback_model_id, temperature=temperature, max_tokens=max_tokens)


def openrouter_available() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY"))


def build_fallback_config(*, temperature: float = 0.15, max_tokens: int = 1024) -> Optional[FallbackConfig]:
    if not openrouter_available():
        return None
    return FallbackConfig(on_rate_limit=[build_openrouter_model(temperature=temperature, max_tokens=max_tokens)])
