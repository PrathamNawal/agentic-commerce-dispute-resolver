# Agent Brief: Agentic Commerce Dispute Resolver

## 1. Problem Statement

AI purchasing agents (e.g. via Stripe's Agentic Commerce Protocol) now complete transactions
autonomously on a user's behalf — and when something goes wrong (a duplicate charge from a
buggy tool-call retry, a guardrail the agent ignored, a listing the agent misread), platforms
have no purpose-built way to figure out who's at fault: the buyer, the merchant, or the
purchasing agent itself. Today that triage is done ad hoc by human support teams reading raw
transaction and agent-action logs case by case, slowly and inconsistently.

**This agent solves:** it autonomously classifies the fault, applies the matching policy, and
resolves (or explicitly escalates) an AI-agent-purchase dispute in seconds — with a cited
rationale and a drafted buyer-facing response — so a human only has to look at the cases that
genuinely need judgment.

## 2. User Persona

| Field | Detail |
|---|---|
| Name | Commerce Ops / Trust & Safety Lead |
| Who | Owns the dispute-resolution pipeline for a platform where AI agents transact autonomously on behalf of users |
| Context | Deploys this system so it runs unattended on every incoming dispute; only sees the cases it explicitly escalates |
| Tech comfort | Comfortable configuring and monitoring an automated system, but not hand-reviewing every case |
| Goal | Resolve the high-volume, low-ambiguity disputes with zero human touch; preserve human judgment for the genuinely hard or high-stakes cases |
| Frustration | Manually reading agent action logs to determine fault is slow, inconsistent across reviewers, and doesn't scale with dispute volume |

## 2a. Job-to-be-Done

> **When I** run a commerce platform where AI purchasing agents complete transactions
> autonomously, **I want to** have disputes triaged and resolved without my team reviewing
> every case, **so I can** spend human review time only on the disputes that actually require
> judgment.

## 3. Input / Output Specification

**Inputs**

| Input | Type | Example | Required |
|---|---|---|---|
| dispute_id | string | "D-001" | Yes (the only external input) |
| transaction record | object (item, amount_usd, purchased_at) | fetched automatically from the transaction log by dispute_id | Yes, system-fetched |
| purchasing agent's action log | list[string] | fetched automatically alongside the transaction record | Yes, system-fetched |
| dispute reason | string | fetched automatically as part of the dispute record | Yes, system-fetched |

**Outputs**

| Output | Format | Description |
|---|---|---|
| decision | enum: refund / replace / deny | The agent's substantive suggested action — always filled in, even when human review is required |
| requires_human_review | boolean | True when policy confidence is low or the amount exceeds the guardrail threshold; the decision above becomes a suggestion for the reviewer rather than an auto-executed action |
| escalation_reason | string or null | Why human review is required, set only when requires_human_review is true |
| amount_usd | float or null | Refund/credit amount, if applicable |
| rationale | string | Explanation citing the applied policy and intake facts |
| buyer_response_draft | string | Customer-facing message explaining the decision |
| review_score | int (0-100) + notes | Independent audit score of the resolution's correctness, policy citation, and tone |

## 4. Step-by-Step Workflow (Plain English)

1. A dispute is filed against a transaction that an AI purchasing agent completed autonomously; its dispute_id enters the pipeline.
2. The Intake Agent pulls the transaction record and the purchasing agent's action log, then writes a neutral summary with an initial fault hypothesis (agent error, merchant error, buyer remorse, or unclear).
3. The Policy Agent looks up the platform's own agentic-commerce dispute policy matching that fault hypothesis, and — where useful — searches the web for real merchant/ACP policy language to ground the decision.
4. The Resolution Agent combines the intake summary and the policy finding to decide its best-judgment action — refund, replace, or deny — and drafts the buyer-facing explanation.
5. A hardcoded guardrail flags the case for human review whenever the policy confidence is low or the dispute amount exceeds a set threshold — the Resolution Agent's decision still stands as its suggestion, it just isn't auto-executed.
6. The Reviewer Agent independently scores the resolution against a fixed rubric (decision correctness, policy citation, tone) before anything is finalized.
7. Low-stakes, high-confidence cases are auto-resolved and the drafted message goes to the buyer; higher-stakes or low-confidence cases are queued for human review instead, carrying the agent's suggested decision.
8. Every run is traced end-to-end, so the ops team can audit exactly why the system reached a given decision after the fact.

## 5. Success Metrics

| Metric | Target | How to Measure |
|---|---|---|
| Decision accuracy vs. gold set | 80%+ | `evals/run_eval.py` comparing predicted decision to `gold_resolution` across the labeled dataset |
| Escalation safety | Zero tolerance for wrongly auto-resolved cases above the escalation threshold; some tolerance for wrongly auto-resolved low-dollar cases | Reviewer Agent's `decision_correct` flag, segmented by transaction amount |
| Latency | Under 30s end-to-end per dispute (4 sequential LLM calls) | Wall-clock time per run, logged via Langfuse trace |
| Human effort per case | Ops reviewer only touches escalated cases, not full volume | % of disputes with `requires_human_review=true` vs. auto-resolved, tracked across eval runs |

## 6. Constraints & Assumptions

**Constraints**
- Zero-cost only: must run entirely on free tiers (Groq inference, Agno framework, Langfuse tracing, uv packaging) — no paid infra
- No real PII or financial data: all transaction and dispute records are synthetic; this must never be wired to a live payments system or real customer data
- No human-in-the-loop for the majority path: the system must be safe to run unattended for the cases it does resolve
- Fixed sequential 4-agent pipeline, not a general router: the only branching logic is the one hardcoded escalation guardrail

**Assumptions**
- The purchasing agent's action log is complete and accurate — the pipeline cannot detect if the log itself was tampered with or incomplete
- The platform policy handbook (currently 4 hardcoded fault categories) covers the dominant real-world fault categories; a real deployment would need a much larger policy corpus
- Groq-hosted Llama models are sufficient reasoning quality for policy interpretation — no model comparison or fine-tuning has been done
- The $200 "low vs. high dollar" escalation threshold is a reasonable stakes proxy — untested against real dispute-cost data

## 7. Contra-Indicators (When NOT to Use This Agent)

| Situation | Why it's unfit | Better alternative |
|---|---|---|
| Suspected fraud or account takeover | Requires investigative/forensic judgment and carries legal exposure, not a policy-lookup decision | Route directly to a dedicated fraud/trust & safety team, bypassing this pipeline |
| Disputes needing real-time payment-processor state | This system reasons over logged records only; it doesn't call live payment APIs | Integrate directly with the processor's dispute API (e.g. Stripe Disputes API) for ground-truth transaction state |
| High-dollar or reputationally sensitive disputes | Wrong autonomous calls at scale carry real financial/legal/PR risk beyond what a rubric score captures | Human review, regardless of policy confidence |
| Novel dispute categories outside the policy handbook | The Policy Agent's handbook covers only 4 fault categories; it will guess or under-cite for anything else | Escalate to a human, and treat it as a signal to expand the handbook |
| Jurisdictions with specific consumer-protection regulation (e.g. EU right of withdrawal) | No compliance/legal grounding is built in | Legal/compliance review before adding policy language for that jurisdiction |

## 8. Data Grounding & Freshness

| Dimension | Detail |
|---|---|
| Data source | Synthetic dispute dataset (`data/disputes.json`) for dev/eval; a hardcoded internal policy handbook; optional live web search for real merchant/ACP policy grounding |
| Knowledge cutoff | The underlying Groq-hosted Llama model has its own training cutoff — any policy reasoning not covered by the handbook or a live search result relies on frozen training knowledge, risking outdated commerce-protocol assumptions |
| Grounding method | Hybrid: structured internal handbook (authoritative but narrow) + ad hoc web search (broad but unverified) — no RAG/vector database |
| Freshness risk | Medium-High — agentic-commerce policy (Stripe ACP and merchant rules) is actively evolving through 2026; the hardcoded handbook goes stale silently unless manually updated |
| Mitigation | Treat the handbook as a living document reviewed on a set cadence; log every case where the Policy Agent falls back to web search as a signal the handbook needs a new entry |
| Upgrade path | Replace the hardcoded handbook with a RAG pipeline over a real, versioned policy corpus, turning freshness into a document-ingestion problem rather than a code-change problem |

## 9. Top 3 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Autonomous wrong resolution on a dispute that should have escalated | Medium | High | Keep the confidence/amount guardrail conservative, extend it beyond a single dollar threshold (e.g. add fault-hypothesis-based escalation), and monitor the Reviewer's `decision_correct` rate segmented by dollar amount |
| Policy handbook goes stale as real ACP/merchant rules change | High | Medium | Quarterly handbook review cadence, plus tracking web-search fallback frequency as an early warning signal |
| Reviewer Agent's scoring is unreliable (an LLM grading LLM output, checked against only a small hand-labeled gold set) | Medium | Medium | Keep growing the gold-labeled dataset, periodically spot-check Reviewer scores against actual human judgment, and use Reviewer scores only for relative before/after comparisons, not as ground truth |

## 10. Learning Objectives (PM Lens)

- Demonstrates structured-output prompting (a Pydantic `output_schema` on every agent) as the mechanism that makes multi-agent chaining and automated evaluation possible at all — this is the single most practical prompt-engineering lesson in the project
- Makes model-configuration tradeoffs concrete: a dispute-resolution agent needs consistent, auditable decisions, which pushes toward structured, low-variance output rather than creative free-form generation
- Key architectural insight: this is a fixed sequential prompt chain with one hardcoded guardrail, not a true autonomous agent with dynamic tool selection or planning — the "4 agents" are really 4 constrained reasoning steps, and that distinction matters for accurately describing what was built
- Natural next-level upgrade: replace the hardcoded policy handbook with real RAG grounding, and replace the single dollar-threshold guardrail with a proper policy-enforcement layer — that's the gap between a portfolio demo and a production-credible system

> **Key insight for this project:** structured outputs turn a chain of LLM calls into a system
> you can actually evaluate — the eval harness only works because every agent is forced to
> speak in a typed schema instead of free text.
