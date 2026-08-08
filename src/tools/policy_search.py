"""Retrieves dispute-resolution policy context for a merchant/agentic-purchase scenario.

Two tools: a small local policy handbook (the platform's own agentic-commerce rules) and
a real web-search fallback for grounding in actual Stripe ACP / merchant policy language.
"""

from duckduckgo_search import DDGS

PLATFORM_POLICY_HANDBOOK = {
    "agent_error": (
        "If the purchasing agent acted outside user instructions, ignored a user-set guardrail "
        "(e.g. price ceiling, cancellation rule), or made a duplicate/erroneous tool call, the "
        "platform refunds the buyer in full. The buyer is never liable for purchasing-agent defects."
    ),
    "merchant_error": (
        "If the listing was materially inaccurate (wrong variant, misleading photo) and the agent "
        "purchased in good faith based on listing data, the merchant must offer replace-or-refund "
        "at no cost to the buyer."
    ),
    "disclosure_failure": (
        "If a purchasing agent completes a purchase without surfacing a material term (final-sale, "
        "no-returns, non-standard shipping) that was present in structured listing data, this is a "
        "borderline case: the merchant policy is technically valid, but the agent's disclosure gap "
        "means the case should be escalated to human review rather than auto-resolved."
    ),
    "buyer_remorse": (
        "Standard return windows (typically 30 days) apply as stated by the merchant when no agent "
        "or merchant error occurred. Process under normal return policy."
    ),
}


def get_platform_policy(fault_category: str) -> str:
    """Return the platform's own agentic-commerce dispute policy for a fault category.

    fault_category must be one of: agent_error, merchant_error, disclosure_failure, buyer_remorse.
    """
    return PLATFORM_POLICY_HANDBOOK.get(
        fault_category,
        "No matching internal policy category; escalate to human review.",
    )


def search_merchant_policy(query: str, max_results: int = 3) -> list[dict]:
    """Web-search for real-world merchant/ACP dispute policy language to ground a decision."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [{"title": r.get("title"), "snippet": r.get("body"), "url": r.get("href")} for r in results]
    except Exception as e:
        return [{"error": f"search unavailable: {e}"}]
