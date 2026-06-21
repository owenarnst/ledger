# Agentic topic discovery, deterministic verification

Status: accepted (2026-06-20)

## Context

The first extraction design made deterministic AST/trail heuristics decide which anchors became worklist Topics and how they ranked. Claude received one already-approved evidence bundle and could only rewrite its title, summary, and invariant. This made the Claude Code harness cosmetic and asked syntax/keyword rules to make semantic judgments about maintenance obligations, trace relevance, and supporting context.

Claude Code is better suited to investigate repository code and development traces, correlate evidence across sources, combine several Decision anchors into one durable Topic, reject syntactic trivia, and explain priority. Deterministic code remains better suited to lossless ingestion, stable identity, exact source resolution, and empirical check validation.

## Decision

Split **discovery** from **verification**:

- Provider adapters and repository scanners deterministically ingest and index commits, code, tests, documentation, comments, and normalized traces. Candidate-anchor detection is a recall-oriented starting point, not the worklist gate.
- A Claude Code **Topic Analyst** uses scoped read-only `Read`, `Grep`, and `Glob` tools to find and interpret supporting Evidence, construct durable Topics, and return the ordered worklist.
- Analyst execution is pinned to Opus with high effort and consumed as `stream-json`. Ledger may expose sanitized phase and tool-use summaries, never private reasoning or source contents. Active output resets a 10-minute inactivity watchdog; there is no short wall-clock deadline on repository investigation.
- Each proposed Topic must contain source locators and link confidence for its anchors and supporting context, plus its maintenance obligation, invariant, risk, and priority explanation.
- Deterministic code resolves cited locators against the indexed sources, rejects unsupported or stale citations, hashes accepted excerpts, and persists immutable Evidence and Topic revisions.
- Checkability and pass/fail remain empirical: baseline-green → mutant-red and test exit codes are not model judgments.

The Topic Analyst is not the Coach. The analyst may inspect repository and trace Evidence because investigation is its purpose. The Coach continues to deny `Read`, `Grep`, `Glob`, `Bash`, and mutation tools so it cannot discover the solution withheld by a Debug-to-Own exercise.

### Minimum Topic proposal contract

Each analyst-proposed worklist item must provide:

- `title`: durable maintenance-obligation name, not a raw symbol;
- `maintenance_obligation` / `invariant`: the behavior a maintainer must preserve;
- `impact_level`: `high`, `medium`, or `low`, plus a grounded failure-consequence explanation;
- `priority`: relative worklist order plus a grounded internal rationale;
- `code_anchors`: one or more source locators with a short relevance statement;
- `development_traces`: zero or more Provider-labeled source locators with relevance and link confidence.

The verifier resolves those locators before accepting the proposal. The UI's **Evidence summary** is derived from the accepted Code-anchor and Development-trace counts; the analyst does not supply an unverified display claim. **Ownership status** is derived from persisted lifecycle and practice history, not invented by the analyst. Detailed worklist and expanded-view presentation requirements live in `docs/planning/ui-spec.md`.

## Consequences

- Worklist membership, grouping, supporting context, and ordering are Claude-generated interpretations grounded by verified sources, not deterministic facts.
- Ledger must record the analyst model, prompt/schema version, input scope, output, citations, and verification result so a worklist proposal is auditable and reproducible enough to debug.
- Model output may vary. Stable Topic identity, immutable revisions, user corrections, citation verification, and the prior accepted worklist prevent that variability from rewriting history silently.
- If analysis is unavailable, Ledger should retain the last verified worklist or expose indexed material as pending analysis; it must not silently present heuristic candidates as equivalent agent analysis.
- Read-only tool access increases the analyst's context and privacy surface. It must be scoped to the enrolled repository and Ledger's normalized local trace store; edit/write, arbitrary shell, web, and unrelated MCP access remain denied.
