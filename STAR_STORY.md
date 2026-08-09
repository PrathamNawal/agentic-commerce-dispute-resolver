# Interview stories: Agentic Commerce Dispute Resolver

Four STAR-format stories drawn from this project, for behavioral/technical interviews or a
portfolio writeup. Every number and detail here is real — pulled from `ROADMAP.md`,
`evals/EVAL_SCORECARD.md`, and actual commits, not reconstructed after the fact.

## 1. The core project story

**Situation:** AI purchasing agents (via protocols like Stripe's Agentic Commerce Protocol)
now complete transactions autonomously on a user's behalf. That creates a new dispute
category platforms have no purpose-built process for: when something goes wrong, is it the
buyer's fault, the merchant's, or the purchasing agent's own error?

**Task:** Build a solo, zero-marginal-cost multi-agent system that triages and resolves these
disputes autonomously, escalating only the cases that genuinely need human judgment —
scoped to be genuinely interview- and portfolio-worthy, not a toy demo.

**Action:** Designed a 4-stage pipeline (Intake → Policy → Resolution → Reviewer), each stage
a single-purpose Agno agent bound to a Pydantic output schema — structured output is what
makes the pipeline chainable and the eval harness possible at all. Deliberately classified the
architecture as a Level 2 prompt chain, not a Level 4 multi-agent system, in the design doc
before writing any code — the four stages always run in the same fixed order, so calling it
"multi-agent" would have been marketing language, not an architectural claim. Built a
guardrail (escalate on low policy confidence, high dollar amount, or an unclear fault
classification) as an auditable prompt rule rather than opaque model judgment, and designed
the human-in-the-loop schema (`requires_human_review` as a separate field from `decision`) so
escalated cases carry a real suggestion for a reviewer instead of a dead end.

**Result:** A working system with a real, honestly-measured baseline: 60% decision accuracy,
90% Reviewer Agent accuracy against ground truth, evaluated across a 10-case labeled dataset
with a full Streamlit demo, CI regression gate, and cross-provider fallback for reliability.
Every one of those numbers came from actually running the system against a live LLM and
finding out what broke — not from a spec.

## 2. "Tell me about a bug you found and how you found it"

**Situation:** The Reviewer Agent — an independent stage meant to audit the pipeline's own
decisions against a labeled gold answer — was reporting `decision_correct=True` on every
single case in the first full eval run, including cases where the actual decision was
objectively wrong.

**Task:** Figure out whether the Reviewer Agent itself was unreliable, or something else was
wrong — before trusting any eval number this system produced.

**Action:** Traced the data flow rather than assuming the LLM was just bad at grading. Found
that `orchestrator.py` was calling `lookup_dispute()` to build the Reviewer's input — the
exact same function used to fetch the Intake Agent's data, which *correctly* strips the gold
answer so Intake never sees the answer it's supposed to reason toward. The Reviewer reused
that same stripped record and never had a gold answer to compare against, despite its prompt
explicitly instructing it to do so.

**Result:** Added `lookup_dispute_with_gold()`, a second lookup function used only by the
Reviewer/eval path. Re-ran the eval: Reviewer accuracy against real ground truth jumped from
0% (structurally incapable of being right) to 90% — with one remaining genuine leniency case,
which is a much smaller, more honest kind of imperfection than "the entire scoring mechanism
was non-functional." The fix mattered more than any prompt tune in the whole project, because
without it, no other number in the system could be trusted.

## 3. "Tell me about a technical tradeoff or judgment call you made"

**Situation:** Groq's free-tier daily token cap got fully exhausted mid-session. Adding an
OpenRouter fallback looked like a simple "if this model fails, try that one" change.

**Task:** Make the pipeline resilient to a full provider outage without overbuilding a
production-grade retry system for a solo demo project.

**Action:** The first attempt — Agno's built-in `fallback_config` — turned out to only cover
an agent's primary `model`, not its `parser_model` (used by two of the four agents to route
around a separate Groq-specific limitation: it rejects JSON-mode structured output combined
with tool calling in one request). Worse, a `parser_model` failure doesn't raise an exception
at all — it silently returns an error string as `.content`, so a naive try/except wouldn't
have caught it either. Rather than fight Agno's internals, wrote an explicit `_run_stage()`
helper in the orchestrator that checks whether the returned content is actually the expected
schema type, and rebuilds the whole agent on OpenRouter if it isn't.

**Result:** Verified live, mid-outage: full 4-stage pipeline, correct decision, 95/100
reviewer score, entirely routed through OpenRouter after Groq failed at every stage. Also
discovered — the hard way, twice — that OpenRouter's free-tier model lineup rotates
(one candidate model had been pulled from the free tier entirely; another had transient
backend timeouts) and that OpenRouter's own free tier caps at 50 requests/day, which a single
full eval run can exhaust on its own. The judgment call: build the resilience layer properly,
but don't pretend free-tier infrastructure is infinitely reliable — document the real limits
instead of hiding them.

## 4. "How do you think about evaluating AI agent quality?"

**Situation:** A dispute-resolution agent that's confidently wrong is worse than one that
says "I'm not sure" — a wrong decision here gets auto-executed and costs real money.

**Task:** Build an eval process that measures this honestly, not one that produces a
reassuring-looking number.

**Action:** Built a gold-labeled 10-case dataset covering edge cases (multi-item bundles,
cross-border fees, an ambiguous-fault case designed specifically to test whether the system
knows when to admit uncertainty). Ran a real baseline (60% decision accuracy), used it to
diagnose the actual failure pattern — not "the model is bad" but specifically "the model
picks a confident wrong category instead of flagging ambiguity" — and shipped a targeted
prompt fix aimed at that exact pattern, not a generic "try to do better" instruction.

**Result:** A fully-scored eval scorecard (composite 66.6/100 against a 70/100 pass bar) that
doesn't hide its own gaps — it explicitly labels which sub-scores are directly observed data
versus reasonable inference from available signals, and states plainly that the before/after
comparison for the prompt fix is still incomplete because of a real infrastructure constraint
(daily rate limits), not because the work wasn't done. The honesty of the scorecard is itself
the point: a scorecard that only ever reports good news isn't measuring anything.
