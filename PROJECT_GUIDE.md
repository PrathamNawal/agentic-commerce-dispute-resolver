# Project Guide: Agentic Commerce Dispute Resolver

**Welcome.** If you're a new PM joining this project, this document is meant to get you from
zero to fully oriented — what this is, why it exists, how it actually works, what's good
about it, what's broken, and where to find everything else. Written in plain language on
purpose; technical terms are explained the first time they show up.

**Live demo:** [agentic-commerce-dispute-resolver.onrender.com](https://agentic-commerce-dispute-resolver.onrender.com/)
**Repo:** [github.com/PrathamNawal/agentic-commerce-dispute-resolver](https://github.com/PrathamNawal/agentic-commerce-dispute-resolver)

---

## Table of Contents

1. [The 30-second version](#1-the-30-second-version)
2. [The problem this solves](#2-the-problem-this-solves)
3. [Who this is for](#3-who-this-is-for)
4. [How it actually works](#4-how-it-actually-works)
5. [The tech stack, and why each piece](#5-the-tech-stack-and-why-each-piece)
6. [How we know if it's any good — evals](#6-how-we-know-if-its-any-good--evals)
7. [What happens when a human needs to step in](#7-what-happens-when-a-human-needs-to-step-in)
8. [Reliability: what happens when the AI provider is down](#8-reliability-what-happens-when-the-ai-provider-is-down)
9. [Key decisions and why we made them](#9-key-decisions-and-why-we-made-them)
10. [Real bugs we found — and what they taught us](#10-real-bugs-we-found--and-what-they-taught-us)
11. [Try it yourself](#11-try-it-yourself)
12. [Where everything lives](#12-where-everything-lives)
13. [What's next](#13-whats-next)
14. [Glossary](#14-glossary)

---

## 1. The 30-second version

AI shopping agents can now buy things for you automatically — you say "get me wireless
earbuds under $100," and an AI agent finds one, checks out, and it's done, no human clicking
"buy." That's genuinely new, and it's called **agentic commerce**.

But when something goes wrong with one of these purchases — wrong item, double charge, a
policy the agent didn't check — **who's supposed to figure out what happened and fix it?**
Today, nobody. There's no standard process for it.

This project is a working prototype of that process: **four AI agents that read the dispute,
find the applicable policy, decide what to do about it, and grade their own decision** — all
without a human, except for the cases that genuinely need one. It's not a toy demo; it's been
tested against a real gold-labeled dataset, it survives real infrastructure outages, and it's
honest about where it's still wrong.

## 2. The problem this solves

**Situation:** A platform lets AI purchasing agents transact on a user's behalf (this is a
real, current thing — Stripe has a protocol for it called ACP, the Agentic Commerce
Protocol). Something goes wrong with one of those purchases.

**Who's at fault?** Could be three different parties:
- **The buyer** — just changed their mind, no real problem occurred (buyer's remorse)
- **The merchant** — sent the wrong item, had a misleading product listing
- **The AI purchasing agent itself** — made a mistake (bought the same thing twice due to a
  bug, ignored a price limit the user set, didn't tell the user about a no-returns policy
  before buying)

**Today's reality:** a human support agent reads through transaction logs and the AI agent's
own action history, case by case, slowly and inconsistently, to figure out who's at fault and
what to do about it.

**What this project does:** automates that triage. Given a dispute, it reads the facts, finds
the policy that applies, decides refund/replace/deny, drafts the reply to the buyer, and
double-checks its own work — in seconds, autonomously, except when the case is genuinely
ambiguous, in which case it explicitly says so and hands off to a human instead of guessing.

## 3. Who this is for

The primary persona (see [`brief/AGENT_BRIEF.md`](brief/AGENT_BRIEF.md) for the full version)
is a **Commerce Ops / Trust & Safety Lead** — someone who owns a platform's dispute pipeline
and wants the high-volume, low-ambiguity cases resolved with zero human touch, while
preserving their team's judgment for the cases that actually need it. Their frustration
today: manually reading agent logs to figure out fault is slow and inconsistent across
different reviewers.

**Job to be done:** "When I run a commerce platform where AI purchasing agents transact
autonomously, I want disputes triaged and resolved without my team reviewing every case, so I
can spend human review time only on the disputes that actually require judgment."

## 4. How it actually works

Every dispute goes through the same four steps, in the same order, every time:

```
Dispute filed
     │
     ▼
┌─────────────────┐   Reads the transaction record and what the AI purchasing
│  1. INTAKE       │   agent actually did. Produces a neutral summary and a
│     AGENT        │   "fault hypothesis": agent_error, merchant_error,
└────────┬─────────┘   buyer_remorse, or unclear.
         ▼
┌─────────────────┐   Looks up the platform's policy that matches that fault
│  2. POLICY       │   category. If needed, searches the web for real merchant
│     AGENT        │   policy language to ground the decision in reality.
└────────┬─────────┘
         ▼
┌─────────────────┐   Decides: refund, replace, or deny. Drafts the message
│  3. RESOLUTION   │   the buyer would actually receive. If the case is risky
│     AGENT        │   (see Section 7), flags it for a human instead of
└────────┬─────────┘   auto-executing.
         ▼
┌─────────────────┐   An independent agent grades the resolution against a
│  4. REVIEWER     │   rubric: is the decision right, does it cite real policy,
│     AGENT        │   is the tone professional? This is the quality-control
└─────────────────┘   step, and it's also what makes the eval system possible.
```

**Important honesty point:** this is technically a **prompt chain**, not a fully autonomous
"multi-agent system" in the more advanced sense (where agents would dynamically decide which
other agent to call, or loop and re-plan). The four steps always run in this exact order —
there's no dynamic routing. Calling it "multi-agent" is common shorthand, but the design doc
is explicit that this is architecturally a simpler, more predictable pattern, and that's a
deliberate choice, not a limitation someone forgot to fix. (See
[Section 9](#9-key-decisions-and-why-we-made-them) for why.)

Each of the four steps is powered by a large language model (LLM — the AI model that does the
actual reading and reasoning, like the technology behind ChatGPT) and is required to respond
in a strict, structured format (a fixed set of fields, not free-form text) — that's what
makes it possible to chain the four steps together reliably and to grade the results at scale.

## 5. The tech stack, and why each piece

This was deliberately built as a **zero-marginal-cost** project — every tool has a free tier,
and the whole thing runs for $0/month under normal use. That's a real constraint that shows
up throughout the project (see Section 8), not just a footnote.

| Layer | Tool | Why |
|---|---|---|
| Agent framework | **Agno** | Handles the mechanics of building an AI agent (giving it tools, enforcing structured output) so we don't hand-roll that |
| AI inference (primary) | **Groq** | Free, very fast responses; has a daily usage cap |
| AI inference (fallback) | **OpenRouter**, then **Gemini** | If Groq is out of capacity, the system automatically tries these next, in order |
| Observability | **Langfuse** | Traces every agent run so you can see exactly what happened and why, after the fact |
| Demo interface | **Streamlit** | The web app you can click around in — Live demo, Eval dashboard, Review queue |
| Hosting | **Render** | Hosts the live demo for free; auto-deploys every time code is pushed to GitHub |
| Packaging | **uv** | Fast, modern Python dependency management |

## 6. How we know if it's any good — evals

**"Eval"** here means: a labeled test set plus an automated way to score the system against
it, so "is this any good" has an actual number attached instead of a gut feeling.

**The gold dataset:** 10 hand-written synthetic disputes in
[`data/disputes.json`](data/disputes.json), each with a human-decided correct answer
(`gold_resolution`) and reasoning (`gold_rationale`). They deliberately cover different
difficulty levels: straightforward cases, a multi-item order, a cross-border customs fee
dispute, a high-dollar case that should escalate regardless of confidence, and — importantly —
one case (**D-009, "Conflicting instructions"**) built specifically to be genuinely
ambiguous, to test whether the system knows when to say "I'm not sure" instead of guessing.

**The real, current numbers** (from [`evals/EVAL_SCORECARD.md`](evals/EVAL_SCORECARD.md), the
full scorecard):

| Metric | Value | What it means |
|---|---|---|
| Decision accuracy | **60%** (6 of 10) | How often the final decision matches the gold answer |
| Reviewer accuracy | **90%** (9 of 10) | How often the self-grading step (Agent #4) correctly judges whether the decision was right |
| Composite rubric score | **66.6 / 100** | A weighted score across decision correctness, reasoning quality, communication tone, and guardrail behavior |
| Pass threshold | 70/100 | The bar we're not clearing yet — stated honestly, not rounded up |

**Why 60% isn't "the system is bad" — it's the point of building evals.** The scorecard
doesn't just report the number, it explains the *pattern* behind the failures: the model
tends to confidently pick a specific fault category (agent error, merchant error, etc.) even
when the actual facts don't clearly support one, instead of admitting the case is ambiguous.
That's a specific, fixable pattern — and a fix for exactly that (a rewritten prompt requiring
the model to only use explicitly-stated facts, never inference, when deciding whether a case
is ambiguous) has already been written and is waiting on quota to re-test (see Section 13).

**This matters for you as a PM:** the value of this project isn't "look, an AI that resolves
disputes" — plenty of demos claim that. The value is the discipline around *measuring* it:
a real labeled dataset, a real scoring rubric, a documented failure pattern, and a specific
fix targeted at that pattern rather than a vague "let's improve the prompt." That loop —
measure, diagnose, fix, re-measure — is the actual skill being demonstrated here.

## 7. What happens when a human needs to step in

The Resolution Agent (step 3) doesn't always auto-execute its own decision. A hardcoded rule
(a **guardrail** — a rule that overrides the AI's judgment for safety, not something the AI
can talk itself out of) forces the case to a human reviewer instead, whenever **any** of
these are true:

1. The Policy Agent's confidence in the matching policy is "low"
2. The dispute amount is over $200
3. The fault is classified as "unclear" (the ambiguous-case scenario from Section 6)

When that happens, the case doesn't just vanish — it's written to a **review queue**
(`outputs/escalations.json`), visible in the demo app's "Review queue" tab, where a human can:

- **Approve** the AI's suggested decision
- **Override** it with their own decision and a reason
- **Request more info** before deciding

Every one of those actions is recorded, and the app computes an **agreement rate** — how
often a human just approves what the AI already suggested. That number is the actual evidence
you'd need before ever loosening these guardrail thresholds — not something to chase for its
own sake, but the real signal that would justify a future decision like "we can raise the
$200 threshold to $500."

## 8. Reliability: what happens when the AI provider is down

This is a bigger deal than it sounds, because this project runs entirely on **free-tier**
infrastructure — and free tiers have real, sometimes surprisingly small, usage limits.

**What we built:**
- **A 3-provider fallback chain**: if Groq (the primary AI provider) is out of capacity for
  the day, the system automatically retries on OpenRouter, then on Gemini, before giving up.
- **Response caching**: identical requests get served from a local cache instead of hitting
  the AI provider again, so repeated testing doesn't burn through the daily quota
  unnecessarily.
- **A proper customer-facing failure state**: if all three providers are genuinely out of
  capacity, the visitor doesn't see a raw error message — they see a plain-language
  explanation ("this demo is temporarily at capacity, not a bug") and a **Try again** button.
  Real bugs (not capacity issues) still show full technical detail, just not thrown at the
  visitor first.

**What we learned the hard way** (documented honestly in [`ROADMAP.md`](ROADMAP.md), not
swept under the rug):
- Free-tier limits are often much smaller than blog posts and documentation suggest — Gemini's
  actual live-tested limit for a fresh account was **5 requests per minute and 20 per day**,
  far below the 250–1,500/day figures found in research. The lesson: verify live, don't trust
  secondhand claims about rate limits.
- Early on, the local development environment and the live production demo were sharing the
  *same* API keys — meaning testing the system locally was silently eating into the quota
  that real visitors to the live site depended on. That's a credential-architecture mistake,
  not a code bug, and it's still an open item to fix (separate keys for dev vs. production).

## 9. Key decisions and why we made them

A few choices were made deliberately, with tradeoffs written down rather than left implicit
(see [`design/DESIGN_DOC.md`](design/DESIGN_DOC.md) for the full reasoning):

- **A fixed 4-step chain, not a dynamic multi-agent system.** Every dispute needs the same
  four steps in the same order — there's no case where you'd skip Intake or run Resolution
  before Policy. Building a system that could dynamically route between agents would add real
  complexity for a capability nothing here actually needs. If a future dispute type needed
  conditional branching, that's the specific point where the architecture would need to change
  — not a redesign of everything.
- **Guardrails as a fixed, auditable rule, not the AI's own judgment.** The Resolution Agent
  can't decide for itself whether to escalate — the three conditions in Section 7 are a plain
  `if` check outside the model's control. A guardrail you can't audit as a fixed rule is a
  worse guardrail.
- **No production payment integration.** This system decides and drafts — it never actually
  moves money. That's a real scope boundary, not an oversight: wiring it to an actual
  refund/replace API is explicitly called out as the next-highest-value addition, and it's
  also exactly the point where a real human sign-off requirement should be added back for
  higher-dollar cases.

## 10. Real bugs we found — and what they taught us

These are documented in detail because they're genuinely useful, not because we're proud of
having bugs. A new PM should read this section closely — it's a realistic picture of what
"building and hardening an AI product" actually looks like day to day, not the polished
after-the-fact story.

**Bug 1 — the self-grading step was structurally incapable of being wrong.** The Reviewer
Agent (step 4) is supposed to check the final decision against the correct answer. Early on,
it reported "correct" on literally 100% of runs — including ones that were objectively wrong.
Root cause: it was never actually given the correct answer to check against, due to a data
plumbing mistake (a function meant to hide the answer from the *other* agents was mistakenly
reused for the Reviewer too). Once fixed, reviewer accuracy became a real, trustworthy 90%.
**Lesson:** a metric that always agrees with you isn't measuring anything — verify your
verifier.

**Bug 2 — a UI button that could never detect being clicked.** While building the "Try again"
button described in Section 8, it silently failed to work — clicking it did nothing. This
turned out to be a fundamental limitation of how the web framework (Streamlit) handles
interactive elements: a button that only appears *inside* another button's result can never
register its own click, because the code that would notice the click only runs when that
*other* button was the one pressed. Diagnosing this required going past assumptions and
adding a temporary debug log to see the actual system state, rather than guessing from what
the browser displayed. **Lesson:** when a fix doesn't behave as expected, get to hard evidence
before concluding anything, especially when your testing tool itself might be part of the
problem.

**Bug 3 — shared credentials between testing and production.** Covered in Section 8: local
development and the live demo used the same API keys, so testing silently degraded the
production experience. **Lesson:** "it works on my machine and it's zero-cost" can hide a real
architectural gap — dev and production environments should never share a finite resource.

## 11. Try it yourself

**No setup — use the live demo:**
[agentic-commerce-dispute-resolver.onrender.com](https://agentic-commerce-dispute-resolver.onrender.com/)
- **Live demo** tab: pick a dispute, click "Resolve this dispute," watch the four agents work
  through it in real time.
- **Eval dashboard** tab: see the actual accuracy numbers from the latest test run.
- **Review queue** tab: see (and act on) any disputes that got escalated to a human.

*Note: the free hosting tier spins the app down after 15 minutes of no traffic — the first
load after that can take 30–60 seconds to wake back up. Not a bug.*

**Running it locally** (for anyone comfortable with a terminal):
```bash
uv sync
cp .env.example .env   # then add a free Groq API key from console.groq.com
uv run streamlit run app.py
```

## 12. Where everything lives

| Document | What's in it |
|---|---|
| [`README.md`](README.md) | Quick-start overview, architecture-vs-production comparison table |
| [`brief/AGENT_BRIEF.md`](brief/AGENT_BRIEF.md) | The original problem framing, persona, success metrics, risks — written before any code |
| [`design/DESIGN_DOC.md`](design/DESIGN_DOC.md) | The technical architecture and every configuration decision, with reasoning |
| [`evals/EVAL_SCORECARD.md`](evals/EVAL_SCORECARD.md) | The full quality scorecard — real numbers, real failure analysis |
| [`ROADMAP.md`](ROADMAP.md) | Everything that's been built, in order, with what was actually learned along the way — the most detailed and current record of the project's real history |
| [`STAR_STORY.md`](STAR_STORY.md) | Interview-ready stories built from this project's real events |
| `src/` | The actual code — one file per agent, plus shared orchestration and configuration |
| `data/disputes.json` | The 10-case gold-labeled test dataset |

**If you only read one other document after this one, read `ROADMAP.md`** — it's a
chronological, honest log of what was built, what broke, and what was learned, which is
usually the fastest way to actually understand a project's real state.

## 13. What's next

Full detail in [`ROADMAP.md`](ROADMAP.md); the short version of what's genuinely still open:

- **Re-run the eval after the ambiguity-detection prompt fix**, to get a real before/after
  comparison (blocked on AI provider quota resetting, not on unfinished work)
- **Separate API keys for local development vs. the live production demo** (the real fix for
  the credential-sharing issue in Section 8)
- **Wire the decision to an actual refund/replace action** (currently: decides and drafts,
  never executes)
- **A written blog post / interview writeup** using the material in `STAR_STORY.md`

## 14. Glossary

- **LLM (large language model)** — the AI model doing the actual reading and reasoning (the
  technology behind tools like ChatGPT)
- **Agent** — here, one focused step in the pipeline: a specific prompt + a specific job (read
  facts, find policy, decide, review)
- **Prompt chain** — a fixed sequence of AI steps, each one's output feeding the next; see
  Section 4 for why this project is technically this, not a more dynamic system
- **Guardrail** — a fixed rule that overrides the AI's own judgment for safety (Section 7)
- **Eval** — a labeled test set plus an automated scoring method, used to measure quality with
  a real number instead of a gut feeling (Section 6)
- **Fallback** — when the primary AI provider is unavailable, automatically trying a backup
  provider instead (Section 8)
- **Rate limit / quota** — a cap a service places on how many requests you can make in a given
  time window (per minute, per day, etc.) — the central constraint behind Section 8
- **Free tier** — the free usage level of a paid service, sufficient for small/solo projects
  but with real caps that a live, public demo can actually hit
