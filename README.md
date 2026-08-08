# Agentic Commerce Dispute Resolver

A multi-agent system that triages and resolves disputes arising from **AI purchasing agents**
transacting on a user's behalf  — not human-typed
support tickets, but disputes where the buyer, the merchant, or the AI shopping agent itself
may be at fault.

Built as a scoped-down, zero-cost implementation of a production agent architecture. See
[Architecture](#architecture) for what's built, what's stubbed, and what's deliberately skipped
— that scoping decision is itself part of the project.

## Why this problem

By 2026, AI shopping agents complete purchases autonomously via protocols like Stripe's ACP.
That creates a new failure surface: duplicate charges from buggy tool-call retries, guardrail
violations (agent ignores a user's price ceiling), listing-disclosure gaps, and the usual
buyer's remorse — all mixed together, and someone (or something) has to adjudicate which is
which before deciding refund / replace / escalate / deny.

## Pipeline

```
Intake Agent  -->  Policy Agent  -->  Resolution Agent  -->  Reviewer Agent
(fault           (which platform     (refund/replace/       (scores the decision
 hypothesis)      policy applies)     escalate/deny +         against a rubric —
                                       buyer-facing draft)     this is the eval seed)
```

Each agent is a single-purpose Agno `Agent` with a structured `output_schema` (see
[`src/schemas.py`](src/schemas.py)) — no agent free-forms its output, which is what makes the
Reviewer's scoring and the eval harness possible.

## Architecture: what's built vs. skipped

Mapped against a full production agent-system reference (client → gateway → orchestrator →
agent core → tools → memory → guardrails → external services → observability):

| Layer | Status | Notes |
|---|---|---|
| Agent Core (4 agents) | **Built** | Intake / Policy / Resolution / Reviewer, each with its own goal, prompt, tools, exit condition |
| Tool Layer | **Built, narrow** | `transaction_log.py` (synthetic dispute records), `policy_search.py` (internal policy handbook + real web search for grounding) |
| Memory | **Built, short-term only** | Each agent reasons over its own context window per dispute; no cross-session/vector memory — a dispute resolver doesn't need it in v1 |
| Observability | **Built** | Langfuse tracing (`src/observability.py`), opt-in via env vars, no-ops if unset |
| Evals | **Built** | `evals/run_eval.py` scores every run against a labeled gold set — see below |
| Guardrails | **Stubbed** | One rule lives in the Resolution Agent's prompt (flag `requires_human_review` if policy confidence is low or amount > $200) rather than a full input-filter/output-check/circuit-breaker stack |
| Human-in-the-loop | **Prep only** | Escalated cases carry a substantive suggested decision (not just a bare flag) and are queued to `outputs/escalations.json`; no review UI yet — see `design/DESIGN_DOC.md`'s roadmap appendix |
| Orchestrator | **Stubbed** | A plain sequential function (`src/orchestrator.py`), not a general router — Agno's Team/Workflow machinery would be the seam to extend if branching logic were ever needed |
| API Gateway, Client layer, Auth, Session mgmt | **Skipped** | This is a CLI script, not a hosted service — no reason to build infra for zero users |

## Setup

Requires [`uv`](https://docs.astral.sh/uv/) and a free [Groq](https://console.groq.com) API key.

```bash
uv sync
cp .env.example .env   # then fill in GROQ_API_KEY (Langfuse keys optional)
```

## Usage

```bash
# Resolve one dispute
uv run main.py D-001

# Resolve every dispute in the dataset
uv run main.py --all

# Run the eval harness against the labeled gold set
uv run evals/run_eval.py
```

## Eval harness

[`data/disputes.json`](data/disputes.json) doubles as the input dataset and the gold set —
each dispute carries a `gold_resolution` and `gold_rationale`. `evals/run_eval.py` runs the
full pipeline over every dispute and reports:

- **Decision accuracy** — does the pipeline's final decision match the gold resolution?
- **Avg reviewer score** — the independent Reviewer Agent's 0–100 rubric score (decision
  correctness, policy citation, tone), averaged across the run

Results are written to `evals/results/` so you can diff runs across prompt or model changes
(e.g. `--model llama-3.1-8b-instant` for a cheaper/faster comparison) and show a before/after
improvement — the actual point of building this.

## Stack

Agno (agent framework) · Groq (inference) · Langfuse (tracing) · uv (packaging) — all free-tier,
zero marginal cost.
