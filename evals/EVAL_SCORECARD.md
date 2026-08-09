# Eval Scorecard — Agentic Commerce Dispute Resolver
> Phase 4: Full | Agentic Commerce Dispute Resolver
> Status: FULL — v1.0 baseline fully scored on real outputs; v1.1 (after-fix) run blocked, see below

**Data provenance:** all scoring below comes from `evals/results/eval_v1.0_baseline.json`, a
complete, real run across all 10 disputes (Reviewer Agent gold-context bug fixed and
confirmed working — see Known Failure Modes). Two sub-checks (fault-hypothesis defensibility)
are *inferred* from directly-observed signals — whether the escalation guardrail fired, and
whether the final decision matched gold — rather than from the exact fault-hypothesis text,
which `run_eval.py` did not log at the time this run executed (it does now — see the harness
fix below). That inference is labeled wherever it's used; everything else is a direct
real value from the run.

**Status of the planned before/after comparison:** the fix (an improved Intake Agent prompt
targeting the fault-hypothesis misclassification pattern, see PM Reflection in the prior
version of this doc) is committed. A second full run to measure its effect was attempted
immediately after and hit **both** Groq's and OpenRouter's daily quotas simultaneously —
a single 10-dispute × 4-stage run apparently consumes most of a fresh daily budget on both
providers when Groq itself is intermittently failing throughout (see `ROADMAP.md`). The
"after" run is still pending; this is the accurate state, not a rounded-up one.

## Section 1 — Test Case Library

| Test ID | Dispute ID | Amount | Dispute reason | Gold resolution | Scenario label |
|---|---|---|---|---|---|
| TC-01 | D-001 | $89.99 | Buyer says delivered color doesn't match listing default | replace | Happy path (single-item, clear-cut merchant error) |
| TC-02 | D-005 | $129.00 | Buyer's remorse, no agent/merchant error | refund | Edge: minimal complexity |
| TC-03 | D-006 | $76.00 | One component of a multi-item bundle arrived defective | replace | Edge: maximal complexity (multi-item) |
| TC-04 | D-007 | $58.00 | Undisclosed customs fee on an international purchase | deny | Niche (cross-border, legitimate-charge dispute) |
| TC-05 | D-009 | $64.00 | Contested prior instruction not captured in the action log | escalate | Stress test (built specifically to probe the unclear-fault guardrail) |

## Section 2 — Evaluation Rubric

### Category 1: Decision Correctness (40 points)
*Does the pipeline reach the right outcome — the thing the whole system exists to get right.*

| Check | Points | TC-01 | TC-02 | TC-03 | TC-04 | TC-05 |
|---|---|---|---|---|---|---|
| Effective outcome matches `gold_resolution` (real, Python-verified) | 30 | 30/30 | 30/30 | 0/30 | 0/30 | 0/30 |
| Suggested decision is a reasonable fallback even when wrong | 10 | 10/10 | 10/10 | 10/10 | 3/10 | 7/10 |
| **Subtotal** | /40 | **40/40** | **40/40** | **10/40** | **3/40** | **7/40** |

TC-03 (D-006) is notable: the guardrail escalated it (effective outcome ≠ gold), but the
*suggested* decision underneath was `replace` — exactly correct. The Resolution Agent's
underlying judgment was right; the guardrail was just conservative. TC-04 (D-007) suggested
`refund` against a gold of `deny` — this is the "biased toward refund" pattern from Known
Failure Modes, not a defensible near-miss.

### Category 2: Reasoning & Policy Grounding (25 points)
*Does the rationale actually justify the decision, or just assert one.*

| Check | Points | TC-01 | TC-02 | TC-03 | TC-04 | TC-05 |
|---|---|---|---|---|---|---|
| Rationale cites a specific policy or fact (real, Reviewer Agent's `cites_policy` flag) | 10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| Fault hypothesis is defensible given the facts (*inferred* — see note below) | 15 | 13/15 | 13/15 | 8/15 | 3/15 | 3/15 |
| **Subtotal** | /25 | **23/25** | **23/25** | **18/25** | **13/25** | **13/25** |

*Inference method for the second row: whether the escalation guardrail fired reveals whether
`fault_hypothesis` was classified as `"unclear"` (TC-03 fired; the rest didn't), and outcome
correctness is strong evidence of reasoning soundness when the guardrail didn't fire. TC-04
and TC-05 both reached a wrong, confident, non-`unclear` classification — the exact failure
pattern this scorecard's v1.1 fix targets. TC-03's guardrail firing could be the
fault-hypothesis dimension or the confidence dimension; scored as genuinely uncertain.*

### Category 3: Buyer Communication Quality (15 points)
*Would a human actually send this message as-is.*

| Check | Points | TC-01 | TC-02 | TC-03 | TC-04 | TC-05 |
|---|---|---|---|---|---|---|
| Professional tone and accurate reflection of the decision (real, Reviewer Agent's `tone_appropriate` flag) | 15 | 15/15 | 15/15 | 15/15 | 15/15 | 15/15 |

Every case scored `tone_appropriate=True` this run — tone was never the problem; decision
correctness was. Worth noting on its own: a system can write a perfectly professional message
around a wrong decision, which is exactly why this category can't be the only one that
matters.

### Category 4: Guardrail & Reviewer Integrity (20 points)
*Does the one safety mechanism in the system actually work — and does the reviewer itself?*

| Check | Points | TC-01 | TC-02 | TC-03 | TC-04 | TC-05 |
|---|---|---|---|---|---|---|
| Escalation guardrail fires when it should (real) | 10 | 10/10 | 10/10 | 5/10 | 3/10 | 0/10 |
| Reviewer Agent's `decision_correct` flag matches real ground truth (real) | 10 | 10/10 | 10/10 | 0/10 | 10/10 | 10/10 |
| **Subtotal** | /20 | **20/20** | **20/20** | **5/20** | **13/20** | **10/20** |

TC-03 (D-006) surfaces a **new, distinct finding**: the Reviewer Agent said
`decision_correct=True` even though the effective outcome (`escalate`) didn't match gold
(`replace`) — a real disagreement with ground truth, now that the Reviewer actually has gold
data to check against (the original bug meant it agreed with *everything*; this is a
narrower, genuine reasoning error, not a data-plumbing bug). Reviewer accuracy across all 10
disputes this run: **9/10 (90%)** — a large, real improvement from the pre-fix 0%, with one
residual leniency case. TC-05 (D-009): the guardrail didn't fire on the exact case it exists
for, consistent with the known failure mode.

## Section 3 — Scoring Summary

| Test Case | Decision /40 | Reasoning /25 | Comms /15 | Guardrail /20 | Total /100 | Pass? |
|---|---|---|---|---|---|---|
| TC-01 (D-001) | 40 | 23 | 15 | 20 | **98** | ✓ |
| TC-02 (D-005) | 40 | 23 | 15 | 20 | **98** | ✓ |
| TC-03 (D-006) | 10 | 18 | 15 | 5 | **48** | ✗ |
| TC-04 (D-007) | 3 | 13 | 15 | 13 | **44** | ✗ |
| TC-05 (D-009) | 7 | 13 | 15 | 10 | **45** | ✗ |
| **Average** | | | | | **66.6/100** | |

**Pass threshold:** 70/100 overall, no category below 60% of its max. 2 of 5 test cases pass;
the average (66.6) sits just below threshold — a real, honest number, not rounded up.
Full-dataset decision accuracy for context: **60% (6/10)**, avg reviewer score **74.0/100**.

## Section 4 — Known Failure Modes

| Failure | Trigger | Impact | Fix |
|---|---|---|---|
| Reviewer Agent had no access to the gold answer | `orchestrator.py` passed the Reviewer Agent the same gold-stripped `lookup_dispute()` record used by Intake (correctly, since Intake must never see the answer) — but Reviewer needs it and never got it | `decision_correct` was `True` on 100% of the first full eval run, including all 5 wrong decisions | **Fixed and verified**: `lookup_dispute_with_gold()` added; this run's reviewer accuracy is 90% (9/10), a real, large improvement — one residual leniency case remains (TC-03/D-006, see Category 4) |
| Fault-hypothesis misclassification on inference-required cases | Cases that require inferring something not literally stated in the action log (TC-04/D-007, TC-05/D-009 this run); the model picks a confident wrong category instead of flagging uncertainty | Wrong fault hypothesis cascades into wrong policy match and wrong final decision — the single biggest driver of the 60% decision accuracy | **Fix applied** (v1.1: rewritten Intake Agent prompt requiring explicit-fact-only reasoning for non-`unclear` classifications) but **not yet re-verified live** — blocked by both providers' daily quotas exhausting in the same session (see below) |
| Unclear-fault guardrail depends on the model admitting uncertainty | D-009 was built specifically to trigger `fault_hypothesis="unclear"`; this run again classified it confidently instead (`predicted_decision=refund`, guardrail never fired) | The guardrail dimension has still not been observed firing on the one case it exists for, across two full runs now | Same v1.1 fix targets this directly; re-verification pending |
| Legitimate charges get defaulted to "refund" | D-007's customs fee was disclosed in structured listing data and should have been denied, not refunded — same result this run | Model appears systematically biased toward the "safe-sounding" refund outcome rather than correctly holding the line on a legitimate charge; now observed twice, not a one-off | Not addressed by the v1.1 fix (that fix targets fault-hypothesis confidence, not decision-direction bias); needs its own targeted iteration once "after" data confirms whether it's still present |
| Groq free-tier daily token cap (100,000 TPD) is easy to exhaust | A single 10-dispute eval run costs roughly 50-60 LLM calls | Can't re-run the full eval more than once or twice per day on the free tier | Implemented: OpenRouter fallback (`src/model_config.py`), verified working live |
| OpenRouter's free tier has its own daily cap (50 req/day) | With Groq intermittently failing throughout a run, most/all calls route through OpenRouter instead of just the overflow | Both quotas exhausted in the same session on two separate days now — blocked the "after" comparison this session specifically | Smaller eval subset for routine iteration (tracked in `ROADMAP.md`); full 10-dispute runs reserved for less frequent checkpoints |

## Section 5 — Prompt Iteration Log

| Version | Change Made | Why | Decision Accuracy | Avg Reviewer Score | Composite (rubric) |
|---|---|---|---|---|---|
| v1.0 | Initial 4-agent pipeline + guardrails | Baseline | **60%** (6/10) | **74.0/100** | **66.6/100** |
| v1.1 | Rewrote Intake Agent's fault-hypothesis instructions: explicit-fact-only reasoning, concrete `unclear` criteria, explicit "confident wrong beats honest uncertain" framing | Directly targets the biggest driver of v1.0's failures (TC-04, TC-05) | **pending** | **pending** | **pending** |

v1.0 here supersedes the earlier, bug-affected 50%/100.0 numbers from the Reviewer Agent's
pre-fix run — that run's decision accuracy (Python-computed, unaffected by the reviewer bug)
was consistent (50%), but its reviewer scores were meaningless. This run's 60%/74.0 is the
first fully trustworthy baseline.

## Section 6 — PM Reflection

- **Most common failure mode:** fault-hypothesis misclassification remains the biggest driver
  — TC-04 and TC-05 both reached a wrong, confident, non-`unclear` classification. The v1.1
  fix targets this directly; whether it actually moves the number is still unverified.
- **Worst-performing test case:** TC-04 (D-007) this run, not TC-05 — 44/100, driven by the
  refund-bias pattern (Known Failure Modes), which the current fix does *not* address. This
  is a genuinely different problem from the unclear-fault guardrail one, and conflating them
  would be a mistake: fixing v1.1 might raise TC-05's score without touching TC-04's at all.
- **A new finding this run, not present before:** the Reviewer Agent, now that it actually has
  gold data, still has one real disagreement with ground truth (TC-03/D-006) — it judged a
  guardrail-triggered escalation as `decision_correct=True` against a gold of `replace`. This
  is a genuine reasoning leniency, not the data-plumbing bug from before. 90% reviewer
  accuracy is good, not perfect — worth tracking as its own number across future runs rather
  than assuming "fixed the bug" means "reviewer is now fully reliable."
- **What requires an architecture change, not a prompt tune:** unchanged from before — the
  unclear-fault guardrail's reliability against a model that's confidently wrong needs an
  independent verification step eventually, not just better wording. The refund-bias pattern
  (TC-04) is a new candidate for the same treatment if v1.2 prompt iteration doesn't resolve
  it either.
