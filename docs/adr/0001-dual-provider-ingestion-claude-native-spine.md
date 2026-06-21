# Dual-provider ingestion, Claude-native spine

Status: superseded by ADR-0004 (2026-06-21)

> **Superseded (2026-06-21):** Codex was dropped entirely — ingestion adapter,
> coach, exercise-generation fallback, and all UI. The `ProviderAdapter`
> abstraction this ADR introduced is kept (now Claude Code + git), but the
> Codex track and the "support both providers" claim no longer hold. See
> ADR-0004. The Context/Decision below are preserved as the original record.

## Context

`docs/planning/product.md:347` framed provider-agnostic support (Cursor/Copilot/ChatGPT/Gemini) as a **roadmap / north-star** item and directed us to *"lead Claude-Code-native — it's the only zero-friction ingestion path, not a compromise."* The thesis and the primary prize (the Anthropic track) are Claude-native by design.

A second engineer has joined who is **Codex-native**. That changes the math: a Codex ingestion adapter becomes cheap to build and test (against the partner's own real Codex sessions, on his own machine), and splitting ownership by provider dissolves the runtime-dependency problem (each engineer owns the provider he can actually run).

## Decision

Pull a **provider abstraction** forward to day 1, but keep the demo **spine** Claude-native:

- Ship a `ProviderAdapter` ingestion interface; the application layer stays provider-blind.
- **Two ingestion adapters:** Owen owns Claude (`~/.claude/projects/**/*.jsonl`); the partner owns Codex. Provenance is **provider-labeled** in the UI (the existing `Claude-authored` chip generalizes to a provider tag).
- As amended by ADR-0002, the **Topic Analyst, hero loop, live SessionStart nudge, and Coach run on Claude Code only.** The Codex adapter is shown at the vision beat as proof the abstraction is real.
- A **Codex / multi-model coach is deferred.** The Coach's defining property is enforced withholding via `--disallowedTools` (the model literally cannot read the sandbox or original code). Codex exposes no equivalent name-based tool-denial primitive, and the raw-API escape reintroduces the API-key + per-token cost the design explicitly killed.

## Gate

A partner **hour-0 feasibility spike** gates the Codex track, mirroring the on-machine verification we did for Claude's data substrate (`product.md:353`):
- (a) Codex must persist local session logs with **tool-call / file-edit granularity** in a parseable format — else the Codex adapter is narrate-only.
- (b) Codex must support a **session-start hook** — else the nudge stays Claude-only.

## Consequences

- `docs/planning/product.md:347` needs reconciliation: provider-agnostic is no longer purely roadmap — *ingestion* is now in scope for two providers. _(Reconciled 2026-06-20: roadmap bullet amended, substrate note cross-referenced, and a Log entry added — see product.md Log 2026-06-20.)_
- "Support both providers" honestly means **ingestion parity + provider-labeled provenance**, not Topic Analyst/Coach/nudge parity. Disclose this distinction if a judge probes.
