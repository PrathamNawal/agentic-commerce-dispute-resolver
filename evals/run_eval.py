"""Eval harness: runs the full pipeline over the gold dataset and reports aggregate accuracy.

This is the artifact for the "I built evals to improve the agent" story: run this before and
after a prompt/model change and diff the numbers.

    uv run evals/run_eval.py
    uv run evals/run_eval.py --model llama-3.1-8b-instant   # cheaper/faster model comparison
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()  # must run before importing src.* — src.observability reads Langfuse env vars at import time

from src.orchestrator import resolve_dispute
from src.tools.transaction_log import load_all_disputes

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def run_eval(model_id: str) -> dict:
    disputes = load_all_disputes()
    rows = []
    correct = 0
    total_score = 0

    for d in disputes:
        result = resolve_dispute(d["id"], model_id=model_id)
        effective_outcome = "escalate" if result.resolution.requires_human_review else result.resolution.decision
        is_correct = effective_outcome == d.get("gold_resolution")
        correct += int(is_correct)
        total_score += result.review.score

        rows.append({
            "dispute_id": d["id"],
            "gold_resolution": d.get("gold_resolution"),
            "predicted_decision": effective_outcome,
            "suggested_decision": result.resolution.decision,
            "decision_match": is_correct,
            "review_score": result.review.score,
            "reviewer_flags": {
                "decision_correct": result.review.decision_correct,
                "cites_policy": result.review.cites_policy,
                "tone_appropriate": result.review.tone_appropriate,
            },
        })

    n = len(disputes)
    summary = {
        "model_id": model_id,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "n_disputes": n,
        "decision_accuracy": correct / n if n else 0,
        "avg_reviewer_score": total_score / n if n else 0,
        "rows": rows,
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="llama-3.3-70b-versatile")
    parser.add_argument("--out", default=None, help="Optional path to write JSON results")
    args = parser.parse_args()

    summary = run_eval(args.model)

    print(f"\nModel: {summary['model_id']}")
    print(f"Disputes evaluated: {summary['n_disputes']}")
    print(f"Decision accuracy: {summary['decision_accuracy']:.0%}")
    print(f"Avg reviewer score: {summary['avg_reviewer_score']:.1f}/100\n")
    for row in summary["rows"]:
        mark = "PASS" if row["decision_match"] else "FAIL"
        print(f"  [{mark}] {row['dispute_id']}: gold={row['gold_resolution']} "
              f"predicted={row['predicted_decision']} score={row['review_score']}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = Path(args.out) if args.out else RESULTS_DIR / f"eval_{summary['model_id'].replace('/', '_')}.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
