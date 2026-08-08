# Design Doc: Agentic Commerce Dispute Resolver

Companion to [`brief/AGENT_BRIEF.md`](../brief/AGENT_BRIEF.md). This document targets the
Streamlit demo as the v1 run environment; the CLI (`main.py`) already implements the same
pipeline and remains the dev/scripting entrypoint underneath the UI.

## 1. Agent Architecture Classification

| Dimension | This Agent | Why |
|---|---|---|
| Pattern | Prompt chain (4 sequential stages, each an Agno `Agent` with a typed output) | Each stage's output is a structured, deterministic input to the next — no stage decides *which* stage runs next |
| Memory | In-context only, scoped to a single dispute | Each dispute is judged independently; nothing about dispute #2 should be influenced by dispute #1 |
| Tools | `lookup_dispute` (transaction/action log), `get_platform_policy` (internal handbook), `search_merchant_policy` (web search) | Ground the Intake and Policy stages in real records/policy instead of the model inventing facts |
| Autonomy level | Level 2 — Prompt chain | See Section 2 for the full rationale |
| Upgrade path | Level 3 (ReAct): a Policy Agent that iteratively decides *whether* to search, how many times, and reformulates its own queries based on what it finds, instead of a fixed one-shot tool call | Only worth it once the policy handbook is large/messy enough that a single lookup stops being reliable |

## 2. Architecture Decision

**What is the minimum autonomy level needed to solve this problem?**

| Level | Pattern | Description | This agent? |
|---|---|---|---|
| 1 | Single LLM call | One prompt in, one response out | ❌ |
| 2 | Prompt chain | Sequential calls, output feeds next | ✅ |
| 3 | ReAct loop | LLM reasons, picks tool, observes, repeats | ❌ |
| 4 | Multi-agent (orchestrator delegates to specialists) | Dynamic routing between specialist agents chosen at runtime | ❌ |

- **Why this level is right:** every dispute goes through the same four reasoning steps in the
  same order — intake, then policy, then resolution, then review. There is no runtime decision
  about *which* agent to call or *whether* to skip one; that's exactly what a prompt chain is
  for, and calling it "multi-agent" (as the project does colloquially) is a naming choice, not
  an architectural one. Being honest about this in the design doc matters more than sounding
  impressive.
- **What would require going higher:** if the Policy Agent needed to decide *how many* searches
  to run, backtrack when a search returns nothing useful, or call a different tool depending on
  merchant type, that's a ReAct loop (Level 3). If disputes needed dynamic routing — e.g. a
  fraud-suspicion sub-agent invoked only for a subset of cases — that's Level 4.
- **What complexity this avoids:** no orchestrator/router logic, no dynamic tool selection, no
  agent-to-agent negotiation. The one piece of dynamic behavior in the system (the
  confidence/amount/unclear-fault escalation guardrail) is a plain `if` check in the
  Resolution Agent's prompt, not agentic reasoning — and that's deliberate, since a guardrail
  you can't audit as a fixed rule is a worse guardrail.

## 3. Workflow Diagram

```
┌──────────────────────┐
│  Dispute filed        │  (dispute_id enters the system —
│  (user input point)   │   triggered automatically, no human types this)
└──────────┬────────────┘
           ▼
┌──────────────────────────────────────────┐
│  INTAKE AGENT                              │
│  tool: lookup_dispute(dispute_id)          │
│  → transaction record + agent action log   │
│  → IntakeSummary{fault_hypothesis, facts}  │
└──────────┬─────────────────────────────────┘
           ▼
┌──────────────────────────────────────────┐
│  POLICY AGENT                              │
│  tool: get_platform_policy(category)       │
│  tool: search_merchant_policy(query)  ─────┼──▶ [web search, optional]
│  → PolicyFinding{policy, source,           │
│                  supports_resolution,      │
│                  confidence}               │
└──────────┬─────────────────────────────────┘
           ▼
┌──────────────────────────────────────────┐
│  RESOLUTION AGENT                          │
│  input: intake summary + policy finding    │
│  guardrail: confidence=low OR amount>$200  │
│             OR fault_hypothesis=unclear    │
│             → set requires_human_review=   │
│               true (decision still filled  │
│               in as a suggestion, never    │
│               blanked out)                 │
│  → Resolution{decision, requires_human_    │
│               review, escalation_reason,   │
│               amount, rationale,           │
│               buyer_response_draft}        │
└──────────┬─────────────────────────────────┘
           ▼
┌──────────────────────────────────────────┐
│  REVIEWER AGENT                            │
│  input: dispute record + all prior outputs │
│  → ReviewScore{decision_correct,           │
│                cites_policy,               │
│                tone_appropriate, score}    │
└──────────┬─────────────────────────────────┘
           ▼
     ┌─────┴──────┐
     ▼            ▼
┌─────────┐  ┌───────────────────┐
│ AUTO-    │  │ QUEUED FOR        │   (output points)
│ RESOLVE  │  │ HUMAN REVIEW      │
│ (send    │  │ (written to       │
│ buyer    │  │  outputs/         │
│ message) │  │  escalations.json)│
└─────────┘  └───────────────────┘
           │
           ▼
   ┌─────────────────┐
   │ Langfuse trace    │  (every run logged for audit,
   │ (observability)   │   regardless of outcome)
   └───────────────────┘
```

## 4. Agent Configuration Sheet

### 4a. Model Parameters

| Parameter | Value | Rationale |
|---|---|---|
| Model | `llama-3.3-70b-versatile` via Groq | Free-tier, tool-calling capable, strong enough for structured-output policy reasoning; matches the zero-cost stack |
| Temperature | 0.15 | Dispute decisions must be reproducible — the same facts should reliably produce the same decision. Low temperature trades away creative phrasing for consistency, which is the right trade for a system making financial calls autonomously |
| Max tokens | 1024 per agent call | Each agent's output is a small structured object (a few fields), not long-form content; caps runaway generation without truncating a valid response |
| Timeout | 20s per agent call | Four sequential calls need to land well under the 30s end-to-end latency target from the brief; 20s per call leaves headroom while still failing fast if Groq is degraded |
| Top-p | default (1.0) | Temperature is the primary control here; no reason to layer nucleus sampling on top for a low-temperature, structured-output task |
| Frequency penalty | not set | No repetition risk in short structured outputs; this parameter matters for long free-form generation, not here |

> **When to change temperature:** raise it only for the `buyer_response_draft` field
> specifically (not the whole agent) if user testing shows the drafted messages read as
> robotic — but keep the `decision` and `rationale` reasoning at low temperature regardless,
> since consistency there is non-negotiable.

### 4b. Prompt Architecture

**System Prompt Role (per agent):** defines the agent's single responsibility, its exit
condition, and — for Resolution — the hardcoded escalation guardrail, so the rule lives in an
auditable instruction rather than being left to model judgment.

```
You are the {Agent Name} in an agentic-commerce dispute resolution pipeline.

Goal: {single responsibility, e.g. "produce a neutral fault hypothesis, do not decide resolution"}

{Guardrail, if any: e.g. "if confidence is low or amount > $200, set requires_human_review=true — still produce your best-judgment decision as a suggestion, never leave it blank"}

Exit condition: {what marks this agent's job done — e.g. "one complete {Schema} produced"}
```

**User Prompt Role:** passes the previous stage's structured output forward as plain-text
context — no re-fetching of data the prior agent already retrieved.

```
{Prior stage's structured fields, e.g.}
Intake summary: {intake.summary}
Key facts: {intake.key_facts}
Policy finding: {policy.applicable_policy} (source: {policy.policy_source})
Policy supports: {policy.supports_resolution} (confidence: {policy.confidence})
```

**Critical constraint:** every agent's output is bound to a Pydantic `output_schema`
(`IntakeSummary`, `PolicyFinding`, `Resolution`, `ReviewScore`). This is non-negotiable — the
orchestrator passes `.content` directly between stages as typed objects, and the eval harness
depends on `resolution.decision` being one of exactly three enum values (refund/replace/deny)
plus the separate `resolution.requires_human_review` boolean, not free text that happens to
contain the word "refund" somewhere.

### 4c. Memory Configuration

| Memory Type | Used? | Notes |
|---|---|---|
| In-context (conversation history) | No | Each agent call is a fresh, single-turn run — no multi-turn conversation state |
| Vector / RAG | No | Policy grounding uses a small hardcoded handbook, not a retrieval index (see Section 6) |
| External DB | No | Disputes are read from a JSON file, not a database, in v1 |
| Session state | No | Each dispute is processed independently; nothing persists between disputes |

**Upgrade path:** adding a vector-indexed policy corpus (replacing the hardcoded handbook)
would let the Policy Agent ground decisions in the actual, current policy text instead of a
maintainer-written summary — this is the single highest-leverage memory upgrade, ahead of
conversation history or session state, which this problem doesn't need at all.

### 4d. Tools Configuration

| Tool | Used? | Notes |
|---|---|---|
| `lookup_dispute` | Yes | Reads the synthetic transaction/action-log record by `dispute_id`; stands in for a real ACP transaction-log API |
| `get_platform_policy` | Yes | Returns the platform's own hardcoded dispute-policy text for a fault category |
| `search_merchant_policy` | Yes | Live DuckDuckGo web search, used by the Policy Agent to ground ambiguous cases in real-world policy language |
| Payment/refund execution API | No | v1 only *decides* and *drafts*; it never actually moves money or triggers a real refund — see Section 5 |
| Database write (audit log persistence) | Partial | Langfuse tracing covers full-run audit; `escalation_queue.py` additionally persists escalated-case decisions to `outputs/escalations.json` (see roadmap appendix) — auto-resolved cases still have no separate DB write beyond tracing |

**Upgrade path:** the highest-value next tool is a real refund/replace execution API — wiring
the Resolution Agent's decision to an actual action (rather than a drafted-but-unexecuted
recommendation) is what would turn this from a decision-support demo into an operational
system. That's also exactly the point where human sign-off should be added back in for
higher-dollar cases, per the brief's contra-indicators.

## 5. Data Flow & Security Notes

- **API key handling:** `GROQ_API_KEY` (and optional `LANGFUSE_*` keys) live in a local `.env`
  file, gitignored, loaded via `python-dotenv`. If leaked, the risk is limited to Groq API
  quota abuse — no payment or customer-data access is gated behind this key.
- **User data sent externally:** transaction amounts, item names, and dispute reasons (all
  synthetic in v1) are sent to Groq for inference, and the Policy Agent's search queries are
  sent to DuckDuckGo. No real PII or payment credentials should ever be constructed into this
  pipeline — this is a hard constraint from the brief, not just a v1 limitation.
- **What's written to disk/logged:** eval results (`evals/results/*.json`, gitignored) contain
  full dispute records and model outputs; Langfuse traces (when enabled) contain the same. Both
  should stay synthetic-data-only for the same reason as above.
- **Third-party retention:** Groq and Langfuse's own data retention policies apply to anything
  sent to them; DuckDuckGo search queries are sent as plain text with no query obfuscation.
  None of this matters while the dataset is synthetic, but it's the first thing to revisit
  before ever pointing this at real dispute data.

## 6. Data Grounding & Freshness

| Dimension | Detail |
|---|---|
| Data source | Synthetic dispute dataset (dev/eval) + hardcoded internal policy handbook + optional live web search |
| Knowledge cutoff | The Llama model's training cutoff is the fallback whenever the handbook and search both come up short — this is invisible to the user unless explicitly flagged |
| Grounding method | Hybrid: structured handbook (authoritative, narrow) + web search (broad, unverified) — no RAG/vector database |
| Freshness risk | Medium-High — agentic-commerce policy is actively evolving through 2026; the handbook goes stale silently without a review process |
| Mitigation | Log every case where the Policy Agent falls back to web search as a signal the handbook needs a new entry; review the handbook on a fixed cadence |
| Upgrade path | Replace the hardcoded handbook dict with a RAG pipeline over a versioned, real policy corpus |

## 7. Eval Success Definition (Pre-Build)

| Criterion | What "good" looks like |
|---|---|
| Decision accuracy | The effective outcome (`"escalate"` if `requires_human_review` is true, otherwise `resolution.decision`) matches `gold_resolution` in at least 80% of the labeled dataset (per the brief's target) |
| Policy citation | `resolution.rationale` references the specific policy category or fact the Policy Agent found — not a generic "per our policy" with no specifics |
| Escalation safety | Zero wrongly-auto-resolved cases (`requires_human_review=false`) above the $200 guardrail threshold; occasional misses tolerated only below it |
| Tone | `buyer_response_draft` reads as professional and non-defensive — a human could send it to a real customer without editing |
| Latency | Full 4-agent pipeline completes in under 30 seconds per dispute |
| Schema validity | Every agent's output parses as its declared Pydantic schema on the first attempt, with no retry needed |

**Minimum bar for v1:** the pipeline must run end-to-end on all 5 seed disputes without a
schema-parsing failure, and decision accuracy must be at or above 80% on that seed set before
any UI work (Streamlit) is considered "done."

## 8. Excalidraw Diagram Notes

- **Colour coding:** blue = user/system input points (dispute filed); purple = agent
  processing steps (Intake, Policy, Resolution, Reviewer); orange = tool calls (lookup,
  policy handbook, web search) branching off their agent box; green = output points
  (auto-resolve, escalate); grey = observability (Langfuse trace), drawn as a sidecar box
  connected to every agent stage rather than inline in the main flow.
- **Arrow labels:** label each arrow between agents with the schema object being passed
  (`IntakeSummary`, `PolicyFinding`, `Resolution`, `ReviewScore`) — this is what makes the
  "structured output is the backbone" point visually obvious.
- **Grouping:** box the four agent stages together in a dashed outer rectangle labeled
  "Prompt Chain (Level 2)" to make the honest architecture classification visible in the
  diagram itself, not just in the text.
- **Special annotations:** mark the Resolution Agent's guardrail check with a red diamond
  ("if confidence=low OR amount>$200 OR fault_hypothesis=unclear → requires_human_review=true,
  decision stays a suggestion") — this is the critical path where autonomy is deliberately
  gated, and it should visually stand out as the one non-linear decision point in an
  otherwise straight-line chain.

## Roadmap

Near-term build/eval/ship work and post-v1 extension points (RAG-based policy grounding,
human-in-the-loop review) live in [`ROADMAP.md`](../ROADMAP.md), not here — keeping status in
one place instead of duplicated across documents.
