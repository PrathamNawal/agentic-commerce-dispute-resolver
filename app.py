"""Streamlit demo: Live demo / Eval dashboard / Review queue.

Run with: uv run streamlit run app.py

This is the presentable-to-a-stranger surface for the project (see design/DESIGN_DOC.md and
ROADMAP.md). main.py remains the scripting/CLI entrypoint the eval harness uses.
"""

import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # must run before importing src.* — src.observability reads Langfuse env vars at import time

import pandas as pd
import streamlit as st

from src.exceptions import CapacityExhaustedError
from src.orchestrator import resolve_dispute_stream
from src.tools.escalation_queue import compute_agreement_stats, load_queue, update_human_action
from src.tools.transaction_log import load_all_disputes

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


def _attempt_resolve(dispute_id: str, model_id: str) -> None:
    """Runs the pipeline and renders the result — or a failure state appropriate to what
    actually went wrong. Capacity issues (rate limits, quota) get a plain-language message,
    not a stack trace; anything else still surfaces real detail, since that's a genuine bug
    someone needs to see. Does NOT render a "Try again" button itself — see
    live_demo_view()'s top-level retry block for why."""
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
    except CapacityExhaustedError as e:
        st.session_state["capacity_failure"] = {"dispute_id": dispute_id, "model_id": model_id, "detail": str(e)}
        st.warning(
            "**This demo is temporarily at capacity.** It runs on free-tier AI infrastructure "
            "with limited daily and per-minute request caps, and just hit one. This isn't a "
            "bug — it usually clears within a minute or two, sometimes longer if a daily cap "
            "was hit. Use \"Try again\" above."
        )
        return
    except Exception as e:
        st.session_state["capacity_failure"] = None
        st.error("Something went wrong resolving this dispute — this looks like a real bug, not a capacity limit.")
        with st.expander("Technical details"):
            st.code(str(e))
        return

    st.session_state["capacity_failure"] = None
    if result:
        render_verdict(result)
        st.caption(
            "Want to see a case that needs a human? Try \"Conflicting instructions\" or "
            "\"High-value wrong item\" above — those escalate instead of auto-resolving."
        )


def live_demo_view() -> None:
    st.markdown(
        "> When an AI shopping agent buys the wrong thing, who's at fault — and who decides?\n\n"
        "This demo walks one real dispute through 4 AI agents that investigate, apply policy, "
        "decide, and self-check the result — end to end, no human required unless the case "
        "genuinely needs one."
    )

    # Rendered unconditionally, every run — not nested inside the "Resolve this dispute"
    # button's branch. A button only detects its own click if the exact same st.button() call
    # executes again on the rerun that click causes; nesting "Try again" inside a branch that
    # only runs when a *different* button is True means "Try again"'s own click is never seen.
    # Confirmed live: the nested version silently ate every retry click. This is the fix.
    failure = st.session_state.get("capacity_failure")
    if failure:
        st.info(
            f"ℹ️ The last attempt on **{failure['dispute_id']}** hit a free-tier capacity "
            "limit. It may work now — or use \"Try again\" below once you've picked a dispute."
        )
        if st.button("Try again", key="retry_top", type="primary"):
            _attempt_resolve(failure["dispute_id"], failure["model_id"])
        with st.expander("Technical details from the last attempt"):
            st.code(failure["detail"])

    disputes = load_all_disputes()
    options = {f"{d['label']} ({d['id']})": d["id"] for d in disputes}
    choice = st.radio("Step 0 — pick a dispute to try", list(options.keys()), horizontal=False)
    dispute_id = options[choice]

    model_id = st.session_state.get("model_id", "llama-3.3-70b-versatile")

    if st.button("Resolve this dispute", type="primary", use_container_width=True):
        _attempt_resolve(dispute_id, model_id)


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
        "Cases the guardrail flagged for human review. Approve the agent's suggestion, "
        "override it with your own decision, or flag that more information is needed."
    )
    queue = load_queue()
    if not queue:
        st.info("Queue is empty. Resolve a dispute that escalates (e.g. \"Conflicting instructions\") to populate it.")
        return

    stats = compute_agreement_stats()
    col1, col2, col3 = st.columns(3)
    col1.metric("Agreement rate", f"{stats['agreement_rate']:.0%}" if stats["agreement_rate"] is not None else "—")
    col2.metric("Reviewed", f"{stats['decided']} / {stats['total']}")
    col3.metric("Pending", stats["pending"])
    st.caption(
        "Agreement rate = approved ÷ (approved + overridden) — how often a human just signs "
        "off on what the agent already suggested. Excludes pending cases and \"request more "
        "info\" (neither is a verdict). This is the evidence needed before ever loosening the "
        "$200 / low-confidence escalation guardrail — not a target to chase for its own sake."
    )
    st.divider()

    for idx, item in enumerate(reversed(queue)):
        amt = f" (${item['suggested_amount_usd']:.2f})" if item.get("suggested_amount_usd") else ""
        with st.container(border=True):
            st.markdown(f"**{item['dispute_id']}** — status: `{item['status']}`")
            st.caption(f"Escalated because: {item['escalation_reason']}")
            st.write(f"Suggested decision: **{item['suggested_decision']}**{amt}")
            st.caption(item["suggested_rationale"])

            if item["status"] != "pending":
                ha = item["human_action"]
                summary = f"Reviewed — **{ha['action'].replace('_', ' ')}**"
                if ha.get("override_decision"):
                    summary += f" → **{ha['override_decision']}**"
                st.success(summary)
                if ha.get("override_reason"):
                    st.caption(ha["override_reason"])
                continue

            col1, col2, col3 = st.columns(3)
            if col1.button("Approve", key=f"approve_{idx}", use_container_width=True):
                update_human_action(item["dispute_id"], item["queued_at"], "approve")
                st.rerun()

            with col2.popover("Override", use_container_width=True):
                new_decision = st.selectbox(
                    "Actual decision", ["refund", "replace", "deny"], key=f"override_decision_{idx}"
                )
                override_reason = st.text_area("Why", key=f"override_reason_{idx}")
                if st.button("Submit override", key=f"submit_override_{idx}"):
                    update_human_action(
                        item["dispute_id"], item["queued_at"], "override",
                        override_decision=new_decision, override_reason=override_reason,
                    )
                    st.rerun()

            with col3.popover("Request more info", use_container_width=True):
                info_note = st.text_area("What's needed?", key=f"info_note_{idx}")
                if st.button("Submit request", key=f"submit_info_{idx}"):
                    update_human_action(
                        item["dispute_id"], item["queued_at"], "request_more_info",
                        override_reason=info_note,
                    )
                    st.rerun()


st.title("Agentic commerce dispute resolver")
tab_live, tab_eval, tab_queue = st.tabs(["Live demo", "Eval dashboard", "Review queue"])

with tab_live:
    live_demo_view()
with tab_eval:
    eval_dashboard_view()
with tab_queue:
    review_queue_view()
