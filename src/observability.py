"""Thin Langfuse wrapper. Tracing is opt-in: if LANGFUSE_* env vars aren't set, every
call below becomes a no-op so the pipeline runs fine without an observability account.
"""

import os

_ENABLED = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))

if _ENABLED:
    from langfuse import observe as _observe
else:
    def _observe(*args, **kwargs):
        def decorator(fn):
            return fn
        if args and callable(args[0]):
            return args[0]
        return decorator


def traced(name: str):
    """Decorator: traces a function as a Langfuse span/generation named `name` when enabled."""
    return _observe(name=name)


def is_tracing_enabled() -> bool:
    return _ENABLED
