# Idempotent worklist reconciliation over an append-only ledger

Status: accepted (2026-06-20)

## Context

ADR-0002 established agentic discovery + deterministic verification for a *single* extraction. It left the **refresh** lifecycle — what happens on the 2nd…Nth run — undefined. Today `extract_or_refresh_topics` re-runs the Analyst on every invocation, keys Topic identity on `file:symbol` (so a rename mints a new Topic and orphans the old, contradicting `CONTEXT.md`'s "a Topic survives renames"), never retires anything, re-inserts Evidence per revision, and stores a single mutable `topics.rank`. Model output varies between runs; without a reconciliation contract that variance would silently rewrite the worklist — and the ownership history attached to it.

## Decision

Treat the **Worklist** as a current projection over an append-only ledger, *reconciled* — never a list the Analyst appends rows into.

1. **Hybrid identity.** A Topic's identity is a stable key anchored to its verified primary Decision anchor (rename/edit-robust), distinct from the per-edit excerpt fingerprint that drives immutable revisions. The Analyst proposes lifecycle operations against stable IDs; deterministic code owns the match. **Matching policy:** confident deterministic anchor-span/excerpt overlap decides on its own; when inconclusive (e.g. rename + move + edit in one commit), the Analyst's `keep(T)` is honored *only if* the new anchor resolves and does not overlap a *different* active Topic; on residual ambiguity or collision it defaults to `create`. The system never wrong-`keep`s a practiced Topic onto changed code — over-creation is cheaply fixable later (`merge`), a wrong `keep` silently corrupts practice history. A rename the matcher can't follow therefore becomes `retire(old) + create(new)`.

2. **Minimal lifecycle: `create` / `update` (with `keep` as the no-op) / `retire`.** `merge` / `split` / `supersede` are deferred (`supersede` later reduces to `retire + create + link`). This scopes `product.md`'s fuller verb set to a v1 that needs only locator + rename-follow matching, not anchor-set-overlap math.

3. **Tiered retire authority.** Code genuinely gone (anchor unresolved *after* rename-follow) → deterministic auto-retire (reversible if it resolves again). Still-resolving + never practiced → Analyst-proposed retire allowed. Still-resolving + practiced → Analyst may only *flag*; removal requires explicit user confirmation. Retire is a state transition, never a row delete.

4. **Two tiers.** *Discovery* — the expensive Analyst investigation that establishes membership + revisions + evidence. *Ranking* — a cheap async pass that orders already-verified Topics for the current context: it consumes Topic metadata + deterministic relevance *signals* (anchor-path proximity to `cwd`, membership in the branch's changed-file set, import distance) + lifecycle facts, and emits an ordered snapshot + a per-item "why now." It orders; it never reads the repo or re-investigates. The live nudge serves the last cached snapshot instantly (nearest/global if the context is unseen) and never computes order on the hot path.

5. **Order is Claude-owned, made cheap by caching — never handed to a heuristic.** Deterministic code owns only *facts* (lifecycle state transitions, applied immediately) and *constraints* (retired/uncheckable never shown). The relative order of active Topics is the last ranking pass's output.

6. **Content-addressed Evidence.** Evidence identity is the content key already named in `product.md:205` (code: commit + blob + path + excerpt hash; trace: session + source-event hash). Persistence is an idempotent UPSERT; `revision_evidence` links shared Evidence to revisions. Deduped within a Topic for v1.

7. **Worklist snapshots.** A snapshot is the immutable ordered output of one ranking pass, keyed by `(topic-set version, context)`; `topics.rank` retires as a stored column. A Topic has three non-conflatable absences: *absent-from-snapshot* (unsurfaced for this context), *active-but-unsurfaced* (still in the ledger), and *retired* (the only exit from active status).

8. **Two input fingerprints.** Discovery fp = `(project, HEAD, trace-set hash, analyst prompt/schema version, model)`; Ranking fp = `(topic-set version, context, ownership version, ranking prompt/model)`. A cache hit skips the corresponding model call. The **trace-set hash** is over the *sorted set* of normalized trace identities (not a timestamp watermark) so backfilled history invalidates it. A forced rerun appends a new `analysis_run` and reconciles via (1) + (6) without duplicating.

9. **Async invocation with a deterministic dirty-gate.** Triggers (post-commit, session-finished, import) recompute the discovery fp behind a cheap gate: changed files vs tracked anchors, Claude/Codex-touched, or high-risk paths mark the project dirty; untracked/low-risk changes defer to a scheduled scan. Dirty projects enqueue a debounced background discovery. The live `SessionStart` nudge **never blocks** — it serves the last verified worklist plus a cheap ranking pass. Anti-triggers (dashboard open, UI navigation, repeated hooks at the same HEAD + trace-set, failed imports) leave both fingerprints unchanged, so nothing runs: the fingerprints *are* the gate.

10. **No syntactic decision-heuristics in discovery or identity.** The deterministic recall index is judgment-free: it enumerates symbols with git blob/path/span and caller-count (a centrality signal) and may *force* high-risk paths (auth/persistence/migrations) into scope, but it never decides what is load-bearing — the Analyst owns that (ADR-0002). AST is retained only for facts that must hold even if the model is wrong: (a) verification-time span resolution and excerpt hashing, and (b) computing the centrality signal the Analyst consumes. Identity matching uses anchor-span overlap over the verifier's *resolved* spans — not a syntactic fingerprint. `extraction.py`'s `_SignalVisitor` ("this syntax is a decision") and `blast_score`'s gate/rank role are removed.

## Considered options

- *Claude owns identity directly* — rejected: puts model nondeterminism on the one thing that must stay stable.
- *Deterministic `file:symbol` identity retained* — rejected: cannot express the lifecycle and breaks "survives renames."
- *Single-tier analysis* — rejected: folding just-in-time context into one fingerprint re-investigates the repo on every navigation.
- *Deterministic re-ranking* — rejected: hands order back to a heuristic, the thing ADR-0002 moved away from.
- *Per-revision Evidence retained* — rejected: re-citation duplicates; idempotency would rest on a guard, not on identity.

## Consequences

- Model variance is contained to wording and order — both safe (wording updates display fields on the same revision; order lands as a new snapshot). It can no longer create/retire Topics or duplicate Evidence.
- A new `worklist_snapshots` table and an Evidence content-key uniqueness constraint are required; `analysis_runs` (already present) records discovery audit. `topics.rank` is superseded by snapshots; migration keeps `rank` as a derived fallback rather than dropping it.
- The live nudge may serve a slightly stale worklist between a triggering change and the background run's completion; this is surfaced via `get_analysis_status`, never presented as fresh.
- `merge` / `split` / `supersede` remain unbuilt; until then a materially different obligation on the same anchor is modeled as `retire + create`.
- Removing `_SignalVisitor` makes the `DeterministicAnalyst` (CI default + offline fallback) intentionally cruder — it surfaces high-centrality enumerated symbols, not heuristically-detected "decisions." The demo currently *relies* on `_SignalVisitor` to surface the hero anchor (`visible_documents_for_tenant`), so `curate-hero` must instead seed that Topic directly (or run the live Analyst), rather than depending on syntactic detection.
