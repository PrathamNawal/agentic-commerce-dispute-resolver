# Roadmap: Agentic Commerce Dispute Resolver

Companion to [`brief/AGENT_BRIEF.md`](brief/AGENT_BRIEF.md) and
[`design/DESIGN_DOC.md`](design/DESIGN_DOC.md). Two kinds of items live here: near-term build
work to get v1 fully working and shippable, and post-v1 extension points that the current
architecture was deliberately designed to absorb without a rework. Check items off as they
land; keep this the single source of truth instead of letting status drift into commit
messages or chat history.

## Phase 3 — Build / Harden

- [ ] **Live smoke test** — run `uv run main.py D-001` with a real Groq key to confirm the
      agents produce sane structured output against a live model, not just static checks —
      *blocked on: `GROQ_API_KEY` in `.env`*
- [x] **Expand the dataset** beyond the 5 seed disputes — now 10, covering multi-item bundles,
      cross-border customs fees, a high-dollar guardrail test, an ambiguous-fault case, and a
      distinct subscription-cancellation failure
- [x] **Second escalation guardrail dimension** — the Resolution Agent now also flags
      `requires_human_review` when the intake `fault_hypothesis` is `"unclear"`, regardless of
      amount or policy confidence (see design doc's Top 3 Risks)
- [x] **Streamlit UI** — `app.py` implements the three-view app (`Live demo`, `Eval
      dashboard`, `Review queue`) against the approved UX: plain-language problem statement up
      top, numbered step-by-step pipeline reveal (via the new `resolve_dispute_stream()`
      generator in `src/orchestrator.py`), one obvious "Resolve this dispute" action, and a
      clean error message instead of a raw traceback when the pipeline fails. Run with
      `uv run streamlit run app.py`. The Review queue view is read-only — approve/override
      actions are still the "planned" item under Human-in-the-loop below
- [ ] **Set up a Langfuse account** and drop keys into `.env` so tracing actually activates
      (currently no-ops silently) — *blocked on: Langfuse signup*

## Phase 4 — Eval (formal scorecard)

- [ ] **Run `evals/run_eval.py` live** once a key is in place — get the real baseline accuracy
      number, not the 80% target
- [ ] **Run `/anthropic-skills:eval-scorecard`** for a structured pass/fail scorecard against
      the criteria in `design/DESIGN_DOC.md` Section 7
- [ ] **Before/after eval comparison** — deliberately weaken or improve a prompt and diff the
      eval numbers; this diff is the actual "I built evals to upskill the agent" artifact
- [ ] **Spot-check Reviewer Agent scores against your own judgment** — an LLM grading LLM
      output is a named risk in the design doc; a handful of manual checks is cheap insurance

## Phase 5 — Ship / Showcase

- [ ] **Deploy the Streamlit demo to Render** (zero-cost stack) so it's a live link, not just
      a repo
- [ ] **GitHub Actions CI** — run the eval suite on every push as a regression check
- [ ] **Write the blog post / LinkedIn writeup** — the scoping-decision narrative (Level 2
      prompt chain, not Level 4 multi-agent; guardrails stubbed on purpose) is the actual
      interview-worthy material
- [ ] **Distill an interview STAR story** — problem, your role, the architecture decision, the
      eval-driven improvement, the result
- [ ] **Cross-link from Agentic PM** — your one project with real signal; pointing traffic
      between the two compounds both

## Post-v1 Extension Points

These aren't scheduled work — they're the two architectural seams the current design was
built to absorb cheaply. Don't build either until there's a real reason to (a policy corpus
that's outgrown the handbook, or an actual reviewer waiting on the queue).

### Policy grounding → vector DB (RAG)

The Policy Agent never touches the handbook directly — it only calls
`get_platform_policy(category: str) -> str` as a tool (`src/tools/policy_search.py`). That
function signature is the frozen contract: category string in, policy-text string out.
Swapping the dict-lookup body for a vector-DB retriever query is a change scoped entirely to
that one function — the Policy Agent, its prompt, and everything downstream never changes.
**Do not** let a future implementation change this function's signature or make it
agent-aware (e.g. passing the whole `IntakeSummary` instead of a category string) without
deliberately re-evaluating this contract.

### Human-in-the-loop

- [x] **Schema split** — `Resolution.decision` is always a substantive suggestion
      (refund/replace/deny), separate from `Resolution.requires_human_review` (bool) and
      `Resolution.escalation_reason`. Escalation no longer discards the agent's judgment — a
      human reviewer always has something concrete to approve or override, never a blank
      flag.
- [x] **Escalation queue** — `src/tools/escalation_queue.py` appends every
      `requires_human_review=True` case to `outputs/escalations.json` with `status: pending`.
      Contract a future review UI reads from: `dispute_id`, `status`, `suggested_decision`,
      `suggested_amount_usd`, `suggested_rationale`, `escalation_reason`, `queued_at`,
      `human_action`. Keep this schema stable; add fields, don't rename them.
- [x] **Review UX — listing view** — the `Review queue` tab in `app.py` lists pending cases
      from `outputs/escalations.json` (dispute ID, status, suggested decision, escalation
      reason). Read-only.
- [ ] **Review UX — actions** — Approve, Override (+ reason), Request more info (state
      reserved, no mechanism yet) buttons that write back to the queue entry's `human_action`
      field. Should reuse the same 4-stage pipeline visual from the live demo so there's no
      new mental model for the reviewer.
- [ ] **Feedback loop** — record the human's action alongside the agent's original suggestion
      in the same queue entry (`human_action`). This produces an agreement-rate metric over
      time — how often a human just approves what the agent already suggested — which is the
      actual evidence needed to justify ever lowering the $200 / low-confidence escalation
      threshold. Escalation stops being a dead end and becomes a calibration signal.
