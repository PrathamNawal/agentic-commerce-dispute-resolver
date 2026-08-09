"""Durable queue for disputes that need human review.

Escalated cases land here so they're inspectable instead of being printed once and discarded.
app.py's Review queue tab reads and writes this file; the schema here is the contract it
depends on. update_human_action() is the feedback-loop write-back: it records what a human
actually decided against the agent's original suggestion, which is what would eventually let
you measure agreement rate and justify tuning the escalation threshold (see ROADMAP.md) — that
aggregate metric itself isn't built yet, only the data collection this makes possible.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

QUEUE_PATH = Path(__file__).resolve().parent.parent.parent / "outputs" / "escalations.json"

ACTION_TO_STATUS = {
    "approve": "approved",
    "override": "overridden",
    "request_more_info": "info_requested",
}


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


def update_human_action(
    dispute_id: str,
    queued_at: str,
    action: str,
    override_decision: Optional[str] = None,
    override_reason: Optional[str] = None,
) -> None:
    """Records a human reviewer's action against a queued escalation. Matched on
    (dispute_id, queued_at) rather than dispute_id alone, since the same dispute could be
    queued more than once across separate runs.

    action must be one of "approve", "override", "request_more_info".
    """
    if action not in ACTION_TO_STATUS:
        raise ValueError(f"unknown action: {action}")

    queue = _load()
    for item in queue:
        if item["dispute_id"] == dispute_id and item["queued_at"] == queued_at:
            item["status"] = ACTION_TO_STATUS[action]
            item["human_action"] = {
                "action": action,
                "override_decision": override_decision,
                "override_reason": override_reason,
                "acted_at": datetime.now(timezone.utc).isoformat(),
            }
            break
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))
