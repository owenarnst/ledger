---
type: project
status: active
owner: Owen
started: 2026-06-19
due: 2026-06-21
tags: [hackathon, code-ownership, build-plan, solo, scope]
related:
  - "[[Ledger]]"
  - "[[UC Berkeley AI Hackathon]]"
---

# Ledger — 24-Hour Solo Build Plan

## Feasibility verdict

The complete product is not possible to build solo in 24 hours. A convincing vertical slice is possible if the scope remains frozen.

Build one real path and simulate the product's breadth without misrepresenting it.

## Solo definition of done

The demo must accomplish exactly this:

1. Claude and Git hooks record activity for one real repository.
2. The local web application shows that project and several seeded ownership topics.
3. One topic is grounded in real code, commit, and session evidence.
4. Starting its check creates a real temporary sandbox with a curated mutation.
5. The browser lets the user edit one file and run a real test.
6. The coach answers conceptual questions without producing a patch.
7. Attempts, elapsed time, reflection, and completion persist in SQLite.
8. The topic page updates after completion.

That is sufficient to demonstrate the product thesis.

## Do not build

- Robust cross-platform installer or daemon
- Automatic topic generation
- Automatic mutant generation
- Arbitrary-repository sandboxing
- Full browser terminal or filesystem
- Reliable tracking through refactors
- Cross-project learning-plan generation
- Ownership scores
- Authentication, cloud sync, teams, or deployment

Use exactly one real Git project with 3–5 seeded topics. One topic is the fully grounded, end-to-end hero path; optionally seed one prior completion to show persistence. Do not add real repositories merely to imply breadth.

## Frozen tech stack

> Resolved in the pre-event stack grill (2026-06-19). Familiar deps only — no learning tax on the critical path. The riskiest pieces (sandbox loop, Claude Code hooks) were already de-risked in Python in the throwaway prototype's `derisk/`; rebuild Saturday, don't carry code to the event.

**Spine — Python-first monolith.**
- **Backend:** FastAPI (Python). Same language as the hero repo, so the test runner is just `pytest` in a subprocess — no cross-language bridge.
- **Frontend:** React + Vite. Owen's most comfortable surface.
- **Hero repo:** a small real **Python** RAG/retrieval repo built *with Claude Code at hour 0, in-window* — **NOT pre-event.** `03_hacker_guide.md:81` requires all projects started during the event (DQ'd every year), and a bespoke demo fixture counts as part of the project. Building with Claude Code yields the same real transcripts + git receipt *whenever* you do it, so hour-0 is rules-clean at a ~1h cost; Ledger ingests the event-period history retroactively (hooks needn't have pre-existed). The pre-event spike repo is a **dry-run template, not the fixture** (its transcripts are pre-event too). **Not Omnibay code** (hard wall + can't show proprietary code publicly).

**Sandbox model — language-agnostic loop, one Python adapter built.**
- Loop: copy repo → apply curated mutation (substring/AST edit to one file) → run the project's own test command as a subprocess → red → user edits in browser → re-run → green.
- **Exit code is the oracle** (exit 0 = green) — language-agnostic; never let the verdict depend on parsing test-output counts (that's UI-only).
- Per-language variation lives in a thin **test adapter** `{setup cmd, test cmd, exit-code convention}`. Build **one adapter: Python/pytest.**
- **Pre-bake the environment** — deps/venv already installed; the temp-dir copy reuses the existing interpreter and copies *source only*. "Create sandbox" = copy files + apply mutant (fast, can't fail on network). No `pip install` at check-time.
- **No containers** — temp-dir + subprocess is enough for a trusted, curated hero repo (spike-proven). Containers/isolation are only for untrusted arbitrary repos → roadmap.
- **Narrate as roadmap:** the adapter registry (TS/Go/Rust), real dependency-provisioning, container isolation — i.e. "arbitrary-repository sandboxing" (already in *Do not build*).

**Editor — Monaco, textarea fallback.**
- `@monaco-editor/react` primary (VS Code editor, free Python highlighting, credible to a dev-tool judge); plain monospace `<textarea>` as the hour-8 fallback if Monaco bundling eats time. Both POST the same buffer; the functional path is identical (backend writes the buffer to the mutated file in the temp dir, re-runs pytest).

**Coach — the user's own Claude Code CLI, not the Anthropic API.**
- *Why:* Ledger is local-first and dev-native. Riding the user's existing **Claude Code** auth means **no API key to manage and no per-token cost** — and it makes Ledger Claude-Code-native on *both* halves (hooks for ingestion, CLI for coaching), the register the Anthropic reps reward.
- *Mechanism:* the FastAPI backend shells out per coach question to **`claude -p "<prompt>"`** (headless/print mode) with **`--output-format json`** and parses the `result` field (the JSON object also carries `session_id`, `total_cost_usd`). Prompt can be passed via stdin (10MB cap).
- *Coach policy:* inject via **`--append-system-prompt`** (augments, doesn't replace — `--system-prompt` would strip Claude Code's own agent prompt). 3-field structure (`concept` / `diagnostic_question` / `suggested_observation`) by prompting + parsing; **reject any response containing a code block** at the response layer. (A native JSON-schema flag may exist — verify at build time; don't depend on it.)
- *Withholding the answer is now an enforced permission boundary, not just prompt hygiene:* **deny all tools** — `--disallowedTools "Bash,Read,Edit,Write,WebFetch,Grep,Glob,NotebookEdit,mcp__*"`. With no Read/Bash, the coach literally cannot open the sandbox files, the original code, or the diff. Also keep them out of the prompt. (Belt and suspenders.)
- *Model:* **omit `--model`** so it uses the user's configured default; their Claude Code OAuth session backs the call — no API key. (Resolves the earlier latency-vs-capability question: it's now the user's choice, per their own Claude Code config.)
- *Consequence:* Ledger's only Claude dependency is the **Claude Code CLI itself** — no `anthropic` SDK, no key handling, nothing to provision for a judge.

**Persistence — SQLite via the Python stdlib `sqlite3`** (or SQLModel if an ORM earns its keep). The demo schema stays small (`projects · topics · topic_revisions · evidence · checks · attempts · reflections`); raw SQL keeps the dependency surface minimal. Seed the provenance rows, but keep topic IDs stable and attach the check to an exact revision so the visible persistence model matches the roadmap.

**Transport — plain REST (FastAPI), request/response.** "Run checks" POSTs the buffer → backend writes file + runs pytest → returns `{passed, output, elapsed}`. **No WebSocket / no streaming** — avoids PTY/streaming complexity and matches "don't build an interactive terminal." (The coach call is also a simple request/response.)

**Hooks — reuse the de-risked `derisk/capture/` scripts (Python).** `SessionStart` hook (reads `cwd`/branch → surfaces ranked topics + the notification line) + a git `post-commit` hook for **every commit, not only Claude-assisted work** → both write events to a local spool/SQLite and exit fast; never block Claude Code or git. At `SessionStart`, compare stored HEAD with current HEAD so pulls/rebases/missed hooks cannot leave tracked topics stale.

**Serving / dev layout — monorepo: `uvicorn` serves FastAPI; Vite dev server proxies to it in dev, FastAPI serves the built static bundle for the demo.** `ledger install` is a thin script (create `~/.ledger/ledger.db`, install hooks, start uvicorn) — not a robust installer (out of scope per *Do not build*).

## 24-hour schedule

| Time | Deliverable |
|---|---|
| 0–2h | Application shell, SQLite schema, seeded project and topic |
| 2–5h | Temporary-copy sandbox, curated mutation, real test runner |
| 5–8h | Check workspace: one-file editor, save, run, output |
| 8–10h | Attempt timing, reflection, persistence |
| 10–12h | Restricted conceptual coach |
| 12–14h | Project dashboard and completed-topic history |
| 14–16h | Claude hook ingestion and notification link |
| 16–19h | Full integration, reset command, failure handling |
| 19–21h | Visual polish |
| 21–24h | Buffer, rehearsal, recording, and rest |

Freeze features by hour 16. A working, visually rough demo is substantially more valuable than a polished half-loop.

## Hard checkpoints

- **Hour 5:** The server can create a sandbox and produce the intended failing test.
- **Hour 8:** A browser edit can make that test pass.
- **Hour 12:** Completion evidence persists.
- **Hour 16:** The hook-to-dashboard-to-check flow works.
- **Hour 19:** Stop changing the architecture.

If the hour-8 checkpoint slips, drop Monaco and use a plain code editor or launch the developer's local editor. Never cut the real sandbox and test loop.

## Work to complete before the clock starts

Planning beforehand materially improves the odds:

- Freeze the data model, routes, and screen states.
- Specify the hero repository, test, and exact mutation.
- Write the coach policy and adversarial prompts.
- Choose familiar dependencies and exact setup commands.
- Produce wireframes and demo copy.
- Write the three-minute script and pitch outline.
- Define the reset and fallback procedure.
- Confirm which preparatory artifacts the hackathon permits.

Do not spend pre-event time expanding the concept.

## Solo versus teammate

This build is feasible solo with moderate execution risk. It becomes infeasible as soon as automatic topics, a general sandbox, or learning plans enter the build.

A teammate is optional. Recruit only someone who can independently own user-interface polish while Owen retains the end-to-end sandbox path. A teammate who changes the concept or requires close coordination increases delivery risk.
