"""Shared model construction: Groq primary, OpenRouter + Gemini fallback, disk-cached.

Three things layer together here, all aimed at the same problem — Groq's free-tier daily cap
(100k TPD) is easy to exhaust, and re-running the same eval/demo repeatedly while iterating
wastes calls on inputs that haven't changed:

1. Response caching (cache_response=True) — Agno's built-in disk cache
   (~/.agno/cache/model_responses by default), keyed on the exact message content sent to the
   model. A prompt change naturally busts the cache. CACHE_TTL_SECONDS is bounded, not
   "never expire": Agno's cache key is the *initial* message only, not tool-call results
   fetched mid-run — so editing data/disputes.json without touching a prompt would NOT bust a
   stale cache entry for the same dispute_id. A bounded TTL limits how long that staleness
   risk can live. Pass use_cache=False (e.g. run_eval.py's --no-cache) for runs that must hit
   a live model to mean anything — the before/after eval comparison, specifically.

2. Fallback chain (Groq -> OpenRouter -> Gemini) — handled entirely by
   orchestrator.py's `_run_stage()`, which type-checks each stage's output and rebuilds the
   whole agent on the next provider in FALLBACK_PROVIDER_ORDER if it's wrong. Agents here
   deliberately do NOT also set Agno's built-in `fallback_config` on top of this: that was
   the original design, but it doesn't cover `parser_model` (used by Intake/Policy to route
   around Groq's JSON-mode + tool-calling conflict — a parser_model failure doesn't even
   raise, it silently returns an error string as `.content`), and layering it under
   _run_stage's own retry caused the SAME fallback provider to be tried twice for one
   failure — confirmed live, it doubled Gemini's 5-requests/minute free-tier consumption
   during testing. One explicit, correct retry path beats two overlapping ones.

3. Provider-specific free-tier quirks, confirmed firsthand, not assumed:
   - OpenRouter's free-tier model lineup rotates: "meta-llama/llama-3.3-70b-instruct:free" was
     pulled from the free tier entirely (404); "openai/gpt-oss-20b:free" had transient backend
     timeouts. "nvidia/nemotron-3-super-120b-a12b:free" is the one verified end-to-end.
   - Gemini's free tier is the starkest lesson here. Third-party reporting (checked while
     building this) claimed anywhere from 250 to 1,500 requests/day for Flash models. The
     actual live-confirmed limit for a newly created API key/project, discovered by running
     this exact pipeline, was 5 requests/MINUTE and only 20 requests/DAY for
     gemini-2.5-flash — nowhere close to what was reported, and barely enough for a single
     dispute (6+ calls) let alone a full eval run. This is plausibly a new-project default
     that Google raises with account age/usage history, not a hard ceiling forever — but
     don't assume that without checking. The takeaway isn't "Gemini is bad," it's "checked
     documentation and live-tested behavior can disagree by 10-75x — verify the current
     limit for your own key at https://ai.google.dev/gemini-api/docs/rate-limits before
     counting on any of these numbers, including the ones in this comment."
   Every fallback model is a moving target — verify before assuming any of these still work.
"""

import os
from typing import List

from agno.models.base import Model
from agno.models.google import Gemini
from agno.models.groq import Groq
from agno.models.openrouter import OpenRouter

DEFAULT_OPENROUTER_FALLBACK_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

CACHE_TTL_SECONDS = 3600  # bounded — see module docstring on why this isn't "never expire"

FALLBACK_PROVIDER_ORDER = ["groq", "openrouter", "gemini"]


def build_model(
    model_id: str = "llama-3.3-70b-versatile",
    *,
    temperature: float = 0.15,
    max_tokens: int = 1024,
    timeout: int = 20,
    use_cache: bool = True,
) -> Groq:
    return Groq(
        id=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        cache_response=use_cache,
        cache_ttl=CACHE_TTL_SECONDS,
    )


def build_openrouter_model(*, temperature: float = 0.15, max_tokens: int = 1024, use_cache: bool = True) -> OpenRouter:
    fallback_model_id = os.getenv("OPENROUTER_FALLBACK_MODEL", DEFAULT_OPENROUTER_FALLBACK_MODEL)
    return OpenRouter(
        id=fallback_model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        cache_response=use_cache,
        cache_ttl=CACHE_TTL_SECONDS,
    )


def build_gemini_model(*, temperature: float = 0.15, max_tokens: int = 1024, use_cache: bool = True) -> Gemini:
    # Agno's Gemini wrapper uses max_output_tokens, not max_tokens like Groq/OpenRouter.
    model_id = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    return Gemini(
        id=model_id,
        temperature=temperature,
        max_output_tokens=max_tokens,
        cache_response=use_cache,
        cache_ttl=CACHE_TTL_SECONDS,
    )


def openrouter_available() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY"))


def gemini_available() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY"))


def available_fallback_providers() -> List[str]:
    """Providers (after groq) that have a key configured, in FALLBACK_PROVIDER_ORDER."""
    checks = {"openrouter": openrouter_available, "gemini": gemini_available}
    return [p for p in FALLBACK_PROVIDER_ORDER[1:] if checks[p]()]


def build_provider_model(
    provider: str, *, temperature: float = 0.15, max_tokens: int = 1024, use_cache: bool = True
) -> Model:
    if provider == "openrouter":
        return build_openrouter_model(temperature=temperature, max_tokens=max_tokens, use_cache=use_cache)
    if provider == "gemini":
        return build_gemini_model(temperature=temperature, max_tokens=max_tokens, use_cache=use_cache)
    raise ValueError(f"unknown fallback provider: {provider}")
