# Eval Scorecard — Agentic Commerce Dispute Resolver
> Phase 4: Full | Agentic Commerce Dispute Resolver
> Status: FULL — scored on real outputs, with two known gaps disclosed below

**Data provenance (read this first):** decision-correctness scoring below is computed in
Python against `gold_resolution` (`evals/run_eval.py`), independent of any LLM judgment —
that data is fully trustworthy for all 10 disputes. Qualitative scoring (reasoning quality,
tone, guardrail-specific behavior) requires reading actual generated text, which I have for
2 of the 5 test cases below (D-001, D-009 — captured from live runs this session). The other
3 test cases' qualitative cells are marked **pending** rather than estimated — Groq's free-tier
daily token cap (100,000 TPD) was exhausted mid-session; see Known Failure Modes below for
what happened and why re-running now would just produce another 429.

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
| Effective outcome matches `gold_resolution` (Python-verified) | 30 | 0/30 | 30/30 | 30/30 | 0/30 | 0/30 |
| Suggested decision is a reasonable fallback even when wrong | 10 | 7/10 | pending | pending | pending | 7/10 |
| **Subtotal** | /40 | 7/40 | 30/40* | 30/40* | 0/40* | 7/40 |

\* one sub-check pending live re-run; subtotal reflects only the scored check.

### Category 2: Reasoning & Policy Grounding (25 points)
*Does the rationale actually justify the decision, or just assert one.*

| Check | Points | TC-01 | TC-02 | TC-03 | TC-04 | TC-05 |
|---|---|---|---|---|---|---|
| Rationale cites a specific policy or fact, not a vague claim | 10 | 10/10 | pending | pending | pending | 10/10 |
| Fault hypothesis is defensible given the actual intake facts | 15 | 3/15 | pending | pending | pending | 4/15 |
| **Subtotal** | /25 | 13/25 | pending | pending | pending | 14/25 |

### Category 3: Buyer Communication Quality (15 points)
*Would a human actually send this message as-is.*

| Check | Points | TC-01 | TC-02 | TC-03 | TC-04 | TC-05 |
|---|---|---|---|---|---|---|
| Professional, clear tone | 8 | 8/8 | pending | pending | pending | 8/8 |
| Accurately reflects the decision without overpromising | 7 | 7/7 | pending | pending | pending | 7/7 |
| **Subtotal** | /15 | 15/15 | pending | pending | pending | 15/15 |

### Category 4: Guardrail & Reviewer Integrity (20 points)
*Does the one safety mechanism in the system actually work — this category exists because of a bug found this session.*

| Check | Points | TC-01 | TC-02 | TC-03 | TC-04 | TC-05 |
|---|---|---|---|---|---|---|
| Escalation guardrail fires when its trigger conditions are actually met | 10 | 10/10 | pending | pending | pending | 3/10 |
| Reviewer Agent's `decision_correct` flag matches real ground truth | 10 | 0/10 | 10/10 | 10/10 | 0/10 | 0/10 |
| **Subtotal** | /20 | 10/20 | 10/20* | 10/20* | 0/20* | 3/20 |

\* Reviewer-integrity check is objectively scoreable for all 10 disputes from the pre-fix run
(see Known Failure Modes #1) even without a fresh live run — that data is real, not estimated.

## Section 3 — Scoring Summary

| Test Case | Decision /40 | Reasoning /25 | Comms /15 | Guardrail /20 | Total /100 | Pass? |
|---|---|---|---|---|---|---|
| TC-01 (D-001) | 7 | 13 | 15 | 10 | **45** | ✗ |
| TC-02 (D-005) | 30* | pending | pending | 10* | **Partial** | — |
| TC-03 (D-006) | 30* | pending | pending | 10* | **Partial** | — |
| TC-04 (D-007) | 0* | pending | pending | 0* | **Partial** | — |
| TC-05 (D-009) | 7 | 14 | 15 | 3 | **39** | ✗ |
| **Average (fully-scored TCs only)** | | | | | **42/100** | |

**Pass threshold:** 70/100 overall, no category below 60% of its max. Neither fully-scored
test case clears it. This is the honest number, not a rounded-up one.

## Section 4 — Known Failure Modes

| Failure | Trigger | Impact | Fix |
|---|---|---|---|
| Reviewer Agent had no access to the gold answer | `orchestrator.py` passed the Reviewer Agent the same gold-stripped `lookup_dispute()` record used by Intake (correctly, since Intake must never see the answer) — but Reviewer needs it and never got it | `decision_correct` was `True` on 100% of the first full eval run, including all 5 wrong decisions — the Reviewer Agent was structurally incapable of catching errors | Added `lookup_dispute_with_gold()`, used only by the Reviewer/eval path; fixed in code this session, re-verification blocked by rate limit (see below) |
| Fault-hypothesis misclassification on inference-required cases | D-001 (listing-photo mismatch) and D-009 (contested prior instruction) both require inferring something not literally stated in the action log; the model picks a confident wrong category instead of flagging uncertainty | Wrong fault hypothesis cascades into wrong policy match and wrong final decision — this is the single biggest driver of the 50% decision accuracy | No fix applied yet; candidates are few-shot examples of "when to say unclear" or restructuring Intake's exit condition to require explicit uncertainty checking |
| Unclear-fault guardrail depends on the model admitting uncertainty | D-009 was built specifically to trigger `fault_hypothesis="unclear"` and the resulting escalation guardrail; instead the Intake Agent confidently said `agent_error` | The guardrail dimension added this session has not yet been proven to fire on the one case it exists for — it's real risk, not a null result | Needs a verification step independent of the same model's self-reported confidence, not just a better prompt |
| Groq free-tier daily token cap (100,000 TPD) is easy to exhaust | A single 10-dispute eval run costs roughly 50-60 LLM calls (4 agents × 10 disputes, plus `parser_model` passes for Intake/Policy) | Can't re-run the full eval more than once or twice per day on the free tier; blocked this exact scorecard from being fully live-verified in one session | OpenRouter fallback (already in the zero-cost stack, unused so far) or spreading eval runs across a UTC day boundary |
| Smaller models don't dodge the rate limit | Tried `llama-3.1-8b-instant` as a fallback; its 6,000 TPM cap is lower than a single request's token cost once tool schemas and instructions are included | Can't casually swap to a cheaper/faster model under time pressure | Would need a stripped-down prompt/tool-schema variant specifically for low-context models |
| Legitimate charges get defaulted to "refund" | D-007's customs fee was disclosed in structured listing data and should have been denied, not refunded | Model appears biased toward the "safe-sounding" refund outcome rather than correctly holding the line on a legitimate charge | Needs more labeled examples of this pattern before a targeted prompt fix is justified — one data point isn't enough to prompt-tune against |

## Section 5 — Prompt Iteration Log

| Version | Change Made | Why | Score Before | Score After |
|---|---|---|---|---|
| v1.0 | Initial 4-agent pipeline + guardrails, as built through this session | Baseline | — | 50% decision accuracy; reviewer scores invalid (see Failure Mode #1) |
| v1.1 | Fixed Reviewer Agent's missing gold-context (`lookup_dispute_with_gold`) | Reviewer was structurally unable to score correctness | N/A — data-plumbing fix, not a prompt tune | Pending live re-run (rate-limited) |
| v1.2 (planned) | Address fault-hypothesis misclassification on D-001/D-009-style cases | This is the biggest single driver of the 50% accuracy number | 50%* | — |

\* v1.0's 50% is the number to beat once quota resets and v1.1 can be verified.

## Section 6 — PM Reflection

- **Most common failure mode:** fault-hypothesis misclassification on cases that require
  inferring something beyond the literal action log — the model picks a confident, specific,
  wrong category rather than admitting the facts are ambiguous. This is the root cause behind
  both scored failures (TC-01, TC-05) and shows up again in TC-04's data.
- **Worst-performing test case:** TC-05 (D-009), and not narrowly — it's the case the
  unclear-fault guardrail was built for this session, and the guardrail never got the chance
  to fire because Intake never reported `unclear`. A guardrail that depends on the same model
  admitting its own uncertainty is only as strong as that model's willingness to do so.
- **Single biggest improvement so far:** fixing the Reviewer Agent's missing gold-context —
  not a prompt change at all, a data-plumbing bug. It's the highest-leverage fix in this
  scorecard because without it, no other score in this system could be trusted, including
  every "100/100" the first full run reported.
- **What requires an architecture change, not a prompt tune:** the unclear-fault guardrail's
  reliability. Prompt-tuning Intake to be "more willing to say unclear" only goes so far
  against a model that's confidently wrong. A more robust version would add an independent
  verification step (a second model or a rules-based sanity check) rather than trusting one
  model's self-assessed confidence — that's a Level 3 (ReAct) upgrade, not a wording change,
  and it should stay out of scope until the simpler prompt-tuning path is actually exhausted.
