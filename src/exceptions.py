"""Custom exceptions so the UI layer can tell a known, temporary capacity limit apart from
an actual bug — they deserve very different user-facing treatment. A cold visitor shouldn't
see a stack trace for something that's just "the free tier is busy right now."
"""

CAPACITY_KEYWORDS = (
    "rate_limit", "rate limit", "resource_exhausted", "429",
    "quota exceeded", "quota_exceeded", "requests per day", "requests per minute",
    "tokens per day", "tokens per minute", "free-models-per-day",
)


class PipelineStageError(RuntimeError):
    """A pipeline stage failed on every available provider for an unclear reason — treat as
    a real bug until proven otherwise."""


class CapacityExhaustedError(PipelineStageError):
    """A pipeline stage failed on every available provider, and every failure looked like a
    rate-limit/quota condition — expected free-tier behavior, not a bug."""


def looks_like_capacity_issue(*contents: object) -> bool:
    combined = " ".join(str(c).lower() for c in contents if c)
    return any(kw in combined for kw in CAPACITY_KEYWORDS)
