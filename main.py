"""CLI entrypoint. Usage:

    uv run main.py D-001            # resolve a single dispute
    uv run main.py --all            # resolve every dispute in data/disputes.json
"""

import argparse
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from src.orchestrator import resolve_dispute
from src.tools.transaction_log import load_all_disputes

load_dotenv()
console = Console()


def print_result(result) -> None:
    if result.resolution.requires_human_review:
        status_line = (
            f"[bold yellow]QUEUED FOR HUMAN REVIEW[/bold yellow] — {result.resolution.escalation_reason}\n"
            f"[cyan]Suggested decision:[/cyan] {result.resolution.decision}"
        )
    else:
        status_line = f"[bold green]Auto-resolved: {result.resolution.decision}[/bold green]"

    console.print(Panel.fit(
        f"[bold]{result.dispute_id}[/bold]\n\n"
        f"[cyan]Fault hypothesis:[/cyan] {result.intake.fault_hypothesis}\n"
        f"[cyan]Policy supports:[/cyan] {result.policy.supports_resolution} "
        f"(confidence: {result.policy.confidence})\n\n"
        f"{status_line}"
        + (f" (${result.resolution.amount_usd})" if result.resolution.amount_usd else "")
        + f"\n[cyan]Rationale:[/cyan] {result.resolution.rationale}\n\n"
        f"[cyan]Buyer message:[/cyan] {result.resolution.buyer_response_draft}\n\n"
        f"[bold]Review score: {result.review.score}/100[/bold] "
        f"(decision_correct={result.review.decision_correct}, "
        f"cites_policy={result.review.cites_policy}, "
        f"tone_appropriate={result.review.tone_appropriate})\n"
        f"[dim]{result.review.notes}[/dim]",
        title=f"Dispute {result.dispute_id}",
    ))


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic Commerce Dispute Resolver")
    parser.add_argument("dispute_id", nargs="?", help="Dispute ID to resolve, e.g. D-001")
    parser.add_argument("--all", action="store_true", help="Resolve every dispute in the dataset")
    parser.add_argument("--model", default="llama-3.3-70b-versatile", help="Groq model id to use")
    args = parser.parse_args()

    if args.all:
        for d in load_all_disputes():
            print_result(resolve_dispute(d["id"], model_id=args.model))
        return

    if not args.dispute_id:
        parser.print_help()
        sys.exit(1)

    print_result(resolve_dispute(args.dispute_id, model_id=args.model))


if __name__ == "__main__":
    main()
