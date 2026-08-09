# Roadmap: Agentic Commerce Dispute Resolver

Companion to [`brief/AGENT_BRIEF.md`](brief/AGENT_BRIEF.md) and
[`design/DESIGN_DOC.md`](design/DESIGN_DOC.md). Two kinds of items live here: near-term build
work to get v1 fully working and shippable, and post-v1 extension points that the current
architecture was deliberately designed to absorb without a rework. Check items off as they
land; keep this the single source of truth instead of letting status drift into commit
messages or chat history.

## Phase 3 — Build / Harden

- [x] **Live smoke test** — ran end to end against real Groq/Langfuse keys. Surfaced and fixed
      two real bugs, not just confirmed the happy path:
      1. Groq rejects JSON-mode structured output combined with tool calling in one request.
         The Intake and Policy agents (both tools + `output_schema`) now set `parser_model`
         (a separate untooled Groq call that does the schema parse) — see `src/agents/intake.py`
         and `src/agents/policy.py`.
      2. `main.py`, `app.py`, and `evals/run_eval.py` all imported `src.orchestrator` (which
         imports `src.observability`, which reads Langfuse env vars at *import time*) before
         calling `load_dotenv()` — so tracing silently stayed disabled even with valid keys in
         `.env`. Fixed by moving `load_dotenv()` before any `src.*` import in all three files.
      One real eval finding along the way: D-009 (built to test the unclear-fault guardrail)
      was misclassified as `agent_error` with high confidence instead of `unclear`, so it
      auto-resolved instead of escalating. Left as-is rather than prompt-tuned — that's exactly
      what the eval harness and Phase 4 work below are for.
- [x] **OpenRouter fallback (zero-cost stack's built-in resilience item)** — Groq's free-tier
      daily cap (100k TPD) was fully exhausted mid-session, exactly the scenario the stack
      reference warns about. Set `OPENROUTER_API_KEY` in `.env` and every agent now falls back
      automatically. Two things had to be handled, not one: Agno's `fallback_config` only
      covers an agent's primary `model` — it does not cover `parser_model` (used by Intake and
      Policy to work around Groq's JSON-mode + tool-calling conflict, see the bug above), and
      a Groq failure inside `parser_model` doesn't raise at all, it silently returns an error
      string as `.content`. `src/orchestrator.py`'s new `_run_stage()` helper explicitly
      type-checks each stage's output and rebuilds the whole agent on OpenRouter if it's wrong
      — see `src/model_config.py` for the full explanation. Verified end-to-end while Groq was
      still rate-limited: full 4-stage pipeline, correct decision, 95/100 reviewer score, all
      routed through OpenRouter's `nvidia/nemotron-3-super-120b-a12b:free`. Two other free
      models were tried first and failed — one had been pulled from OpenRouter's free tier
      entirely, the other had transient backend timeouts — confirming firsthand the "lineup
      rotates" warning in the zero-cost toolkit reference
- [x] **Scalable quota strategy** — after repeatedly exhausting Groq + OpenRouter in one
      session, researched and implemented a layered fix rather than just waiting out resets:
      1. **Response caching** (`cache_response=True`, `CACHE_TTL_SECONDS=3600` in
         `src/model_config.py`) — Agno's built-in disk cache, keyed on exact message content.
         Directly targets the actual waste pattern: re-running the same unchanged eval
         multiple times in one session. `--no-cache` on `main.py`/`evals/run_eval.py` forces
         a live call when staleness would be wrong (the before/after comparison, specifically).
      2. **Third fallback tier (Gemini)** — extended `FALLBACK_PROVIDER_ORDER` to
         groq -> openrouter -> gemini. Requires `GOOGLE_API_KEY`.
      3. **Removed a real inefficiency found via live testing**: agents originally set both
         Agno's built-in `fallback_config` AND relied on `_run_stage()`'s explicit retry —
         redundant, since `_run_stage` already covers every failure mode correctly (including
         the parser_model gap Agno's fallback never covered). Layering both meant a single
         failure could hit the same fallback provider twice. Removed `fallback_config` from
         all four agents; `_run_stage` is now the only retry path.
      **Honest result, not a solved-problem story**: live-tested Gemini's actual free-tier
      limit for a fresh API key/project — 5 requests/minute AND only 20 requests/day for
      `gemini-2.5-flash` — nowhere near the 250-1,500/day figures third-party research
      reported. All three providers ended up exhausted in the same session. The caching layer
      and the redundancy fix are real, verified wins; Gemini as a capacity *increase* is
      unproven so far and may just be a new-project default that needs account age/usage
      history to raise — don't assume it solves the volume problem until re-tested after some
      natural usage accrues. Considered and explicitly declined for now: a one-time $10
      OpenRouter top-up (50→1,000 req/day) — cheapest, highest-confidence fix, still on the
      table if the free-only approach keeps being unreliable
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
- [x] **Set up a Langfuse account** and drop keys into `.env` — tracing confirmed active
      (`is_tracing_enabled()` returns `True` after the dotenv-ordering fix above)
- [x] **Both free-tier daily quotas exhausted — confirmed as a recurring pattern, not a
      one-off** — happened on two separate days now. After Groq's 100k TPD cap maxes out,
      OpenRouter's own free-tier cap (50 requests/day — documented in the zero-cost toolkit
      reference, now confirmed the hard way twice) also maxes out on a single full-dataset
      eval re-run, since with Groq intermittently failing, most/all calls route through
      OpenRouter instead of just the overflow. Both reset on a fixed daily boundary
      (OpenRouter: confirmed midnight UTC via its `X-RateLimit-Reset` header), not a rolling
      window — retrying sooner just wastes calls. This is a real operating constraint of the
      zero-cost stack for an agent this token-hungry, not a bug to fix — see Phase 4's
      before/after item for the specific thing it's currently blocking. Longer-term: a
      10-dispute eval run is expensive relative to a 50/day free budget; worth considering a
      smaller "smoke" eval subset (3-4 disputes) for routine iteration and reserving the full
      10-dispute run for less frequent checkpoints

## Phase 4 — Eval (formal scorecard)

- [x] **Run `evals/run_eval.py` live** — real baseline: **50% decision accuracy** (5/10),
      well below the 80% target. Also caught a real bug (see below) that means the *avg
      reviewer score* from this run (100/100) is invalid — decision accuracy itself is not,
      since it's computed in Python against `gold_resolution`, not by the LLM
- [x] **Spot-check Reviewer Agent scores against your own judgment** — this is what caught
      the bug: `decision_correct=True` on literally every case in the first run, including
      all 5 wrong decisions. Root cause: the Reviewer Agent never received `gold_resolution`
      (it was stripped by the same `lookup_dispute()` the Intake Agent correctly uses to avoid
      seeing the answer). Fixed via a new `lookup_dispute_with_gold()`, used only by the
      Reviewer/eval path. Named as a risk in the design doc before it was ever observed —
      worth noting that predicting a risk and then actually catching it are different things
- [x] **Run `/anthropic-skills:eval-scorecard`** — [`evals/EVAL_SCORECARD.md`](evals/EVAL_SCORECARD.md)
      now has a fully-scored v1.0 baseline: **60% decision accuracy (6/10), 74.0 avg reviewer
      score, 66.6/100 composite rubric score**, all 5 test cases scored (no pending cells) —
      real data across the board, with fault-hypothesis defensibility explicitly labeled as
      inferred from observable signals rather than fabricated. Also caught a *new*, narrower
      Reviewer Agent finding beyond the original bug: 90% reviewer accuracy (9/10) against
      real ground truth, with one genuine leniency case (not a data-plumbing bug this time —
      see scorecard Category 4)
- [x] **Fault-hypothesis misclassification fix (v1.1)** — rewrote the Intake Agent's prompt
      (`src/agents/intake.py`) to require explicit-fact-only reasoning before choosing a
      non-`unclear` fault category, with concrete criteria for when `unclear` is the right
      call. Directly targets the biggest driver of v1.0's failures (TC-04/D-007, TC-05/D-009
      in the scorecard). Code is committed; **not yet verified live**
- [ ] **Before/after eval comparison** — the "before" half is now fully real and complete
      (v1.0: 66.6/100 composite, see scorecard). The "after" run (v1.1, with the fix above)
      was attempted immediately and **hit both Groq's and OpenRouter's daily quotas in the
      same session** — a single 10-dispute run apparently consumes most of a fresh daily
      budget on both providers when Groq is intermittently failing throughout. **Re-run
      `uv run evals/run_eval.py --out evals/results/eval_v1.1_after_fix.json` once quota
      allows**, then diff against v1.0 in the scorecard's Section 5. This is the one piece of
      Phase 4 still genuinely incomplete — not for lack of trying, for lack of quota

## Phase 5 — Ship / Showcase

- [x] **Deploy the Streamlit demo to Render** — live at
      [agentic-commerce-dispute-resolver.onrender.com](https://agentic-commerce-dispute-resolver.onrender.com/).
      Blueprint connected, env vars set, service builds and serves correctly. **Functional
      verification pending**: the first live resolve attempt hit the same exhausted Groq +
      OpenRouter daily quotas as the rest of this session — and the app handled it exactly as
      designed, showing the clean `st.error` message (see `app.py`) instead of crashing, which
      is itself a real confirmation the error-handling work holds up in production, not just
      locally. Try resolving a dispute again once quota resets to confirm the full live path.
      Free tier spins down after 15 min idle (cold start ~30-60s) — expected, not a bug
- [x] **GitHub Actions CI** — [`.github/workflows/eval.yml`](.github/workflows/eval.yml) runs
      the eval harness on every push/PR to `main`, gated on a 30% decision-accuracy regression
      floor (deliberately below the ~50% baseline to absorb normal LLM run-to-run variance,
      not the 80% aspirational target — raise it as real fixes land). Results upload as a
      build artifact. **You still need to add the `GROQ_API_KEY` secret yourself** —
      `gh secret set GROQ_API_KEY` or Settings > Secrets and variables > Actions — I can't do
      this on your behalf (submitting an API key to a third-party service, even your own
      GitHub, is something you need to do directly)
- [ ] **Write the blog post / LinkedIn writeup** — the scoping-decision narrative (Level 2
      prompt chain, not Level 4 multi-agent; guardrails stubbed on purpose) is the actual
      interview-worthy material
- [x] **Distill an interview STAR story** — [`STAR_STORY.md`](STAR_STORY.md): the core project
      pitch plus three sub-stories (the Reviewer Agent bug, the OpenRouter fallback tradeoff,
      the eval-honesty philosophy) — every number pulled from real commits and the scorecard,
      not reconstructed after the fact

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
- [x] **Review UX — actions** — Approve, Override (+ reason), Request more info buttons in the
      `Review queue` tab, writing back to the queue entry's `human_action` field via
      `update_human_action()` in `src/tools/escalation_queue.py`. Verified live in-browser:
      all three actions tested end-to-end (Approve, Override → correct decision + reason,
      Request more info → note captured), status updates correctly (`approved` /
      `overridden` / `info_requested`), and acted-on items switch to a read-only summary.
      Matched on `(dispute_id, queued_at)` rather than `dispute_id` alone, since the same
      dispute can be queued more than once across runs.
- [~] **Feedback loop** — the write-back mechanism above *is* this: every human action is now
      recorded alongside the agent's original suggestion in the same queue entry. What's still
      missing is the aggregate view — an agreement-rate metric (how often a human just
      approves what the agent already suggested) computed across the queue over time. That's
      the actual evidence needed to justify ever lowering the $200 / low-confidence escalation
      threshold, and it doesn't exist yet — the data to compute it from does now.
