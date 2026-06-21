# Drop Codex; single-provider Claude-native, selectable coach model

Status: accepted (2026-06-21)

Supersedes the dual-provider parts of ADR-0001.

## Context

ADR-0001 pulled a `ProviderAdapter` abstraction forward to day 1 and shipped a
second **Codex** ingestion adapter, betting on a Codex-native partner who would
own it against his own real sessions. The bet's premise no longer holds: Codex
is no longer being maintained in this build, so the Codex adapter, the
half-built `CodexCoach`, and the Codex exercise-generation fallback are
unexercised code paths that carry runtime-dependency and provenance risk
(`codex` on PATH, an untested log format) without buying a demonstrated
capability.

Separately, the Coach was always Claude-only by design (enforced withholding via
`--disallowedTools`; ADR-0001, CONTEXT.md). The only Coach knob a maintainer
actually wants is **which Claude model answers** — a cost/quality dial, not a
provider switch.

## Decision

1. **Drop Codex entirely.** Remove the `CodexAdapter`, `CodexCoach`, the Codex
   exercise-generation fallback, and every Codex mention from the UI
   (enrollment log-sources list, coach selector, provenance chip). `codex` is no
   longer in `SUPPORTED_PROVIDERS`; ingestion now refuses it (HTTP 400).
2. **Keep the `ProviderAdapter` abstraction.** The application layer stays
   provider-blind. The shipped adapters are now **Claude Code** (conversation
   provenance) and **git** (code reality). Provenance stays provider-labeled, so
   a future adapter can be added without touching the spine.
3. **Selectable coach model.** The coach selector now chooses a Claude model —
   `haiku | sonnet | opus`, **default `sonnet`** — threaded through
   `create_coach(model)` → `ClaudeCoach.model_id` → `claude -p --model …`,
   mirroring `ClaudeAnalyst.model_id`. An unknown model is rejected. Overridable
   via `LEDGER_COACH_MODEL`.

## Consequences

- The "support both providers" framing from ADR-0001 / `product.md` no longer
  holds and is reconciled there. The honest claim is now: Claude-native spine
  with a provider-blind ingestion abstraction (Claude Code + git).
- `docs/adr/0003` still mentions a "Claude/Codex-touched" dirty-gate heuristic;
  that is historical — only Claude/git remain.
- The coach gains a real cost/quality lever (Haiku for cheap/fast, Opus for
  hardest topics) without ever weakening enforced withholding — `--model` is
  orthogonal to `--disallowedTools`.
- API change: the coach endpoints take `model` instead of `provider`; the
  response echoes the resolved `model`.
