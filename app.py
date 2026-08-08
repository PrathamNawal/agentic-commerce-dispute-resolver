"""Streamlit demo: Live demo / Eval dashboard / Review queue.

Run with: uv run streamlit run app.py

This is the presentable-to-a-stranger surface for the project (see design/DESIGN_DOC.md and
ROADMAP.md). main.py remains the scripting/CLI entrypoint the eval harness uses.
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.orchestrator import resolve_dispute_stream
from src.tools.escalation_queue import load_queue
from src.tools.transaction_log import load_all_disputes

load_dotenv()

st.set_page_config(page_title="Agentic Commerce Dispute Resolver", layout="centered")

STAGE_META = {
    "intake": ("1", "Read the facts", "Pulls the order and what the shopping agent actually did."),
    "policy": ("2", "Find the rule", "Looks up the policy that applies to this kind of mistake."),
    "resolution": ("3", "Make the call", "Decides refund, replace, or deny — and drafts the reply."),
    "review": ("4", "Double-check itself", "An independent agent grades the decision before it ships."),
}

RESULTS_DIR = Path(__file__).resolve().parent / "evals" / "results"


def render_stage(stage: str, payload) -> None:
    if stage == "intake":
        st.write(f"**Fault hypothesis:** {payload.fault_hypothesis}")
        st.caption(payload.summary)
    elif stage == "policy":
        st.write(f"**Policy found:** {payload.applicable_policy}")
        st.caption(f"Confidence: {payload.confidence} · supports: {payload.supports_resolution}")
    elif stage == "resolution":
        amt = f" (${payload.amount_usd:.2f})" if payload.amount_usd else ""
        st.write(f"**Suggested decision:** {payload.decision}{amt}")
        st.caption(payload.rationale)
    elif stage == "review":
        st.write(f"**Reviewer score:** {payload.score}/100")
        st.caption(payload.notes)


def render_verdict(result) -> None:
    res = result.resolution
    amt = f" (${res.amount_usd:.2f})" if res.amount_usd else ""
    if res.requires_human_review:
        st.warning(f"**Queued for human review** — {res.escalation_reason}\n\nSuggested: **{res.decision}**{amt}")
    else:
        st.success(f"**Auto-resolved: {res.decision}**{amt}")
    st.write(res.rationale)
    st.markdown("**Buyer message:**")
    st.info(res.buyer_response_draft)


def live_demo_view() -> None:
    st.markdown(
        "> When an AI shopping agent buys the wrong thing, who's at fault — and who decides?\n\n"
        "This demo walks one real dispute through 4 AI agents that investigate, apply policy, "
        "decide, and self-check the result — end to end, no human required unless the case "
        "genuinely needs one."
    )

    disputes = load_all_disputes()
    options = {f"{d['label']} ({d['id']})": d["id"] for d in disputes}
    choice = st.radio("Step 0 — pick a dispute to try", list(options.keys()), horizontal=False)
    dispute_id = options[choice]

    model_id = st.session_state.get("model_id", "llama-3.3-70b-versatile")

    if st.button("Resolve this dispute", type="primary", use_container_width=True):
        result = None
        st.markdown("**Watch it work — 4 steps, no human in the loop unless flagged**")
        try:
            for stage, payload in resolve_dispute_stream(dispute_id, model_id=model_id):
                if stage == "done":
                    result = payload
                    break
                num, label, blurb = STAGE_META[stage]
                with st.status(f"Step {num} — {label}", state="complete", expanded=True):
                    st.caption(blurb)
                    render_stage(stage, payload)
        except Exception as e:
            st.error(
                "Couldn't resolve this dispute — check that `GROQ_API_KEY` is set in `.env` "
                f"and valid.\n\nDetails: {e}"
            )
            return
        if result:
            render_verdict(result)
            st.caption(
                "Want to see a case that needs a human? Try \"Conflicting instructions\" or "
                "\"High-value wrong item\" above — those escalate instead of auto-resolving."
            )


def eval_dashboard_view() -> None:
    st.markdown("Aggregate accuracy against the labeled gold set — the actual point of building evals.")

    result_files = sorted(RESULTS_DIR.glob("eval_*.json")) if RESULTS_DIR.exists() else []
    if not result_files:
        st.info(
            "No eval run yet. From a terminal with a Groq key configured, run:\n\n"
            "`uv run evals/run_eval.py`\n\nthen reload this page."
        )
        return

    chosen = st.selectbox("Eval run", [f.name for f in reversed(result_files)])
    data = json.loads((RESULTS_DIR / chosen).read_text())

    col1, col2, col3 = st.columns(3)
    col1.metric("Decision accuracy", f"{data['decision_accuracy']:.0%}")
    col2.metric("Avg reviewer score", f"{data['avg_reviewer_score']:.0f}/100")
    escalated = sum(1 for r in data["rows"] if r["predicted_decision"] == "escalate")
    col3.metric("Escalation rate", f"{escalated / len(data['rows']):.0%}" if data["rows"] else "—")

    df = pd.DataFrame(data["rows"])[
        ["dispute_id", "gold_resolution", "predicted_decision", "suggested_decision", "decision_match", "review_score"]
    ]
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"Model: {data['model_id']} · run at {data['run_at']}")


def review_queue_view() -> None:
    st.markdown(
        "Cases the guardrail flagged for human review. Approve/override actions aren't built "
        "yet — see ROADMAP.md's human-in-the-loop section — this is a read-only view of the "
        "queue `escalation_queue.py` writes to."
    )
    queue = load_queue()
    if not queue:
        st.info("Queue is empty. Resolve a dispute that escalates (e.g. \"Conflicting instructions\") to populate it.")
        return

    for item in reversed(queue):
        amt = f" (${item['suggested_amount_usd']:.2f})" if item.get("suggested_amount_usd") else ""
        with st.container(border=True):
            st.markdown(f"**{item['dispute_id']}** — status: `{item['status']}`")
            st.caption(f"Escalated because: {item['escalation_reason']}")
            st.write(f"Suggested decision: **{item['suggested_decision']}**{amt}")
            st.caption(item["suggested_rationale"])


st.title("Agentic commerce dispute resolver")
tab_live, tab_eval, tab_queue = st.tabs(["Live demo", "Eval dashboard", "Review queue"])

with tab_live:
    live_demo_view()
with tab_eval:
    eval_dashboard_view()
with tab_queue:
    review_queue_view()
