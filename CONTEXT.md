# Ledger

A local Claude-Code-native companion that keeps a repo-level **ownership ledger** for AI-assisted code: it surfaces load-bearing decisions shipped without a reasoning trail, then tests whether you can still operate them by breaking one and asking you to fix it.

> Canonical product truth lives in `docs/planning/product.md`; build constraints in `docs/planning/build-plan.md`; interaction/layout in `docs/planning/ui-spec.md`. This file is the **glossary** — terms only, no implementation.

## Language

**Topic**:
The durable, repository-specific maintenance obligation a maintainer needs the *why* of to change the system safely. Survives renames and rewrites.
_Avoid_: function, symbol, mutation (those are where a Topic shows up, not the Topic).

**Decision anchor**:
The concrete code artifact where a Topic shows up — a threshold, branch, chosen dependency, control-flow ordering, or access check.
_Avoid_: high-fan-in symbol (load-bearing means a defendable *decision*, not a common symbol).

**Concept**:
A generalized learning pattern derived across multiple Topics (e.g. *isolation boundaries*); always linked back to its source Topics, never free-floating.

**Check**:
One point-in-time Debug-to-Own exercise against a specific code revision of a Topic — break the decision, observe the failing test, repair it.

**Attempt**:
A single pass at a Check. Struggle (elapsed, runs, coach use) is the signal — never the binary solve.

**Evidence**:
Immutable records (code / conversation / docs / commit / test) that ground a Topic. Conversation evidence carries a **Provider** tag.

**Provider**:
The coding-agent harness that authored a trace — currently **Claude Code** or **Codex**. A provenance fact and a ranking signal, never a validation input.

**Provider adapter**:
The ingestion component that normalizes one Provider's local session logs into Ledger Evidence records. The application layer is provider-blind; only adapters are provider-specific.

**Coach**:
The restricted assistant that explains concepts/goals and asks diagnostic questions but never returns a patch. Runs Claude-only (`claude -p`, all tools denied); see ADR-0001.

**Blast radius**:
How much breaks if a decision is wrong — centrality (callers/fan-out) + risk-class (auth, persistence, migrations, irreversible). The static "does it matter" axis.

**Ownership thinness**:
The personal "do *you* own it" axis — decay state (`never checked → practiced → code changed since → revisit due`), boosted by AI-authorship.
_Avoid_: transcript-engagement (a dead signal — see Flagged ambiguities).

**AI-authorship**:
A binary provenance fact from the **Receipt**: did an agent author/touch this decision. A ranking booster, never a gate, never a validation input.

**Receipt**:
The provider-labeled view of the conversation **Evidence** that authored or last touched a **Decision anchor** — proof of **AI-authorship**, anchored to the code and the commit where it landed. Progressively discloses the grounded layers (L1 collapsed provenance summary → L2 expanded prompt + tool-call hunk → L3 raw source record); it renders what the trace contains and never asserts a reasoning trail (the thinness is _visible_, not _computed_). Provider-blind in layout; layers absent from a Provider's logs are simply hidden.
_Avoid_: anchoring on a tuned magic number (a threshold's "why" is "I tried values" — not a defendable decision).

## Relationships

- A **Project** contains many **Topics**; a **Topic** has many revisions.
- A **Check** targets exactly one Topic revision; an **Attempt** belongs to one Check.
- A **Topic** is grounded in **Evidence**; conversation Evidence comes from a **Provider** via that Provider's **Provider adapter**.
- Ranking = a gate (load-bearing ∧ untrailed) then **Blast radius** + **Ownership thinness**; **AI-authorship** boosts, never gates.
- **Concepts** are derived from multiple Topics and always retain links back to them.
- A **Topic**'s **Receipt** renders the conversation **Evidence** for its **Decision anchor**; **AI-authorship** is read off the Receipt. The Receipt is provenance display only — never a validation input.

## Example dialogue

> **Dev:** "Is a high-fan-in helper like `encode()` a **Topic**?"
> **Domain expert:** "No — that's a common symbol, not a defendable **decision**. A **Decision anchor** is something like the rerank threshold or the tenant-isolation check: if you can't form a 'defend this choice' question, it's trivia, not a Topic."

## Flagged ambiguities

- **"load-bearing"** was used to mean high-fan-in *symbol*; resolved — it means a defendable *decision* (an early build that ranked by raw fan-in surfaced trivia).
- **"engagement"** (transcript-engagement classification) is a dead signal that failed validation; it is never an input to Ownership thinness or to any Provider judgement. Use **AI-authorship** (a binary provenance fact) instead.
- **"support both providers"** (this event) means **ingestion** parity + provider-labeled provenance; the **Coach** and the live session nudge run on **Claude Code only**. See ADR-0001.
