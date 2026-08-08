"""Durable queue for disputes that need human review.

No review UI exists yet (that's the human-in-the-loop roadmap item in DESIGN_DOC.md) — this
is the prep step so escalated cases land somewhere inspectable instead of being printed once
and discarded. A future review UI reads this file directly; the schema here is the contract
it depends on.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

QUEUE_PATH = Path(__file__).resolve().parent.parent.parent / "outputs" / "escalations.json"


def _load() -> list[dict]:
    if not QUEUE_PATH.exists():
        return []
    return json.loads(QUEUE_PATH.read_text())


def queue_for_review(
    dispute_id: str,
    suggested_decision: str,
    suggested_amount_usd: float | None,
    suggested_rationale: str,
    escalation_reason: str,
) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    queue = _load()
    queue.append({
        "dispute_id": dispute_id,
        "status": "pending",
        "suggested_decision": suggested_decision,
        "suggested_amount_usd": suggested_amount_usd,
        "suggested_rationale": suggested_rationale,
        "escalation_reason": escalation_reason,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "human_action": None,
    })
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))


def load_queue() -> list[dict]:
    return _load()
