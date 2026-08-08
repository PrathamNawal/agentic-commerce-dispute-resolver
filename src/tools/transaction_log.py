"""Reads synthetic dispute/transaction records. Stands in for a real ACP transaction-log API."""

import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "disputes.json"


def lookup_dispute(dispute_id: str) -> dict:
    """Look up a dispute's transaction details and the purchasing agent's action log by dispute ID."""
    disputes = json.loads(DATA_PATH.read_text())
    for d in disputes:
        if d["id"] == dispute_id:
            return {
                "id": d["id"],
                "buyer_agent": d["buyer_agent"],
                "merchant": d["merchant"],
                "transaction": d["transaction"],
                "agent_action_log": d["agent_action_log"],
                "dispute_reason": d["dispute_reason"],
            }
    return {"error": f"no dispute found with id {dispute_id}"}


def load_all_disputes() -> list[dict]:
    return json.loads(DATA_PATH.read_text())
