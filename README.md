# Ledger

**A local, Claude-Code-native companion that keeps a repo-level ownership ledger for AI-assisted code.** It finds load-bearing code decisions shipped without a reasoning trail, ranks them by how much they matter and how thin the ownership evidence is, then asks the maintainer to prove they can still operate them — by breaking one and asking them to fix it.

> *"Claude Code makes developers faster. Ledger makes sure they still own what they ship."*

Ledger is pro-responsible-use, not anti-AI. The villain is **silent epistemic debt**: AI makes it frictionless to ship working code without ever building the model of it in your head, and the most safety-critical casualty is debugging — [Anthropic's own RCT](https://www.anthropic.com/research/AI-assistance-coding-skills) found it's the single largest skill gap in AI-assisted developers. Ledger operationalizes that finding: it catches which decisions may be hard to maintain later, and makes developers earn the understanding back.

---

## What it does

Ledger is a **finite-attention allocator**. Nobody can deeply own their entire codebase, and checking evenly is waste — so Ledger keeps a running, decaying ledger of where ownership is thin *on the things that matter*, and surfaces the highest-leverage gaps in priority order.

* **Selects** — the **Topic Analyst** (a scoped Claude Code harness with read-only `Read`/`Grep`/`Glob`) investigates the repository and its real Claude session traces to construct an ordered **worklist** of durable maintenance obligations. Deterministic code then verifies every citation, hashes the evidence, and persists it. No item exists without exact code grounding.
* **Surfaces just-in-time** — a `SessionStart` hook reads the current `cwd`/branch and surfaces debt *on the path about to be touched*, with deep links into the app.
* **Verifies (Debug-to-Own)** — starting a **Check** spins up a real temp-dir sandbox of the committed code, injects a small blast-controlled semantic defect targeted at the flagged decision, and asks the maintainer to diagnose and repair it until the test suite goes green. The signal is *struggle* — time, attempts, coach use — never the binary solve.
* **Coaches without leaking** — the **Coach** runs on the user's own Claude Code CLI (`claude -p`, **all tools denied**), so it explains concepts, asks diagnostic questions, and suggests experiments but *architecturally cannot* hand over the patch. The user picks which Claude model answers (`haiku | sonnet | opus`, default `sonnet`).
* **Remembers** — topics, evidence, attempts, and reflections persist in a local SQLite ledger across sessions and code changes; a tracked decision that gets modified again, especially if still untrailed or previously fumbled, re-surfaces to the top.

Ledger **recommends checks; it never asserts that someone lacks understanding** and never grades code. The headline is *"this deserves a check,"* inferred from silence — only the check result turns a candidate into confirmed debt.

## How it works

```text
Git commits + code/tests/docs + real Claude session traces (~/.claude/projects/**/*.jsonl)
  → deterministic lossless ingestion + searchable indexes        (backend/ingestion.py, extraction.py)
  → Claude Code Topic Analyst investigates with scoped Read/Grep/Glob   (backend/analyst.py)
  → structured, ordered Topic proposals with source locators + confidence
  → deterministic citation verification + immutable evidence records   (backend/verifier.py)
  → create / revise / retire topics; project the ordered worklist
  → Debug-to-Own Check: sandbox + targeted mutation + real test    (backend/sandbox.py, exercise_*.py)
  → attempts + Coach use + reflection                              (backend/coach.py)
  → future commit / relevance / time trigger → repeat
```

Provenance model: **code is truth** (what gets exercised), **docs/ADRs/comments are the trail** (whether the *why* was captured), **the transcript is the receipt** (whether Claude was involved). The transcript is deliberately kept *out* of validation — diff↔session linking is fuzzy — and is stored as provenance display only.

## Architecture

* **Backend** — Python 3.11+ / FastAPI (`backend/`). SQLite-backed append-oriented ledger (`backend/db.py`, `repository.py`), the agentic analyst + deterministic verifier, the sandbox + mutation engine, the coach, and the hook/CLI surface (`backend/__main__.py`, `hooks.py`). Sandboxes are temp-dir + `subprocess` with **exit-code-as-oracle** — no containers, no interactive terminal.
* **Frontend** — React + Vite + TypeScript (`frontend/src/`). Three screens: `Dashboard` (the worklist + why each item is ranked), `Topic` (progressively-disclosed evidence + ownership history), and `Workspace` (Task / Sandbox-editor / Coach panes).
* **Hooks** — global Claude Code `SessionStart` + git `post-commit`. They are Ledger's *sensory system*, not its interface: if the server is down they spool to a local file and exit fast, and **must never block Claude Code or git.**

## Requirements

* **Python ≥ 3.11**
* **Node.js** (for the Vite frontend)
* **Claude Code CLI** on the user's `PATH` — Ledger's only Claude dependency. The Topic Analyst and Coach shell out to `claude -p`; users ride their existing Claude Code auth, so there's no API key to manage and no per-token cost.

## Quick start

```bash
# 1. Install dependencies (backend editable install + frontend npm install)
make install

# 2. Seed the curated demo worklist into ~/.ledger (wipes + re-seeds the DB and sandboxes)
make reset

# 3. Start the app (frontend on :4317, backend API on :8000)
make dev
```

Then open **http://localhost:4317**.

> The seeded demo ships a fully-grounded **tenant-isolation** hero topic and its Debug-to-Own check, so the full loop can be shown end-to-end: worklist → topic card → sandbox → coach → repair → reflection → persisted history. Curated components are disclosed as curated.

### Running against a real repository

Point the analyst at a Git repo to discover its worklist. Extraction ingests that repo's *real* `~/.claude` transcripts as Agent-trace evidence.

```bash
# Deterministic analyst (no Claude calls)
make extract REPO=~/Projects/your-repo

# Live Claude Code Topic Analyst — cites the real prompts + tool calls per topic
make extract-claude REPO=~/Projects/your-repo
```

To wire the hooks into a repo so sessions and commits are captured automatically:

```bash
.venv/bin/python -m backend install --repo ~/Projects/your-repo
```

## Make targets

| Command                          | What it does                                                                                       |
| -------------------------------- | -------------------------------------------------------------------------------------------------- |
| `make install`                   | Install frontend (`npm install`) and backend (`pip install -e ".[dev]"`) dependencies              |
| `make dev`                       | Start frontend (`:4317`) and backend (`:8000`) together                                            |
| `make frontend` / `make backend` | Start one side only                                                                                |
| `make reset`                     | Reset `~/.ledger` to the curated Claude demo worklist (wipes DB + sandboxes, re-seeds the fixture) |
| `make seed-demo`                 | Alias for `make reset`                                                                             |
| `make extract REPO=…`            | Discover the worklist for `REPO` via the deterministic analyst                                     |
| `make extract-claude REPO=…`     | Same, but run the live Claude Code Topic Analyst (`LEDGER_ANALYST=claude`)                         |
| `make clean`                     | Remove `node_modules`, `dist`, and Python build artifacts                                          |

`make help` lists them in the terminal.

## Configuration

| Variable             | Default         | Purpose                                                                                                                          |
| -------------------- | --------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `LEDGER_ANALYST`     | `deterministic` | Analyst backend for `extract`; set to `claude` for the live Topic Analyst                                                        |
| `LEDGER_COACH_MODEL` | `sonnet`        | Which Claude model the Coach answers with (`haiku` / `sonnet` / `opus`) — a cost/quality dial, never a relaxation of withholding |

Local state lives under `~/.ledger/` (`ledger.db` + `sandboxes/`). The app serves on `http://127.0.0.1:4317`.

## Development

```bash
# Backend tests (run from the repo root, against the in-repo .venv)
pytest

# Frontend type-check and tests
cd frontend
npm install          # once
npm run typecheck
npm run test
```

The CLI surface (`python -m backend …`) exposes `reset`, `extract`, `nudge`, `drain-spool`, `spool-commit`, `session-start`, and `install` — see `backend/__main__.py`.

## Project layout

```text
backend/            FastAPI app, analyst, verifier, sandbox, coach, hooks, SQLite ledger
  fixtures/         curated demo seed + the hero-repo sandbox tree
  tests/            pytest suite
frontend/src/       React/Vite app — Dashboard, Topic, Workspace screens
docs/
  adr/              architecture decision records (0001–0004)
  agents/           how agents should use the issue tracker, triage labels, domain docs
  planning/         canonical product spec, build plan, UI spec
CONTEXT.md          the domain glossary — terms and relationships, no implementation
CLAUDE.md           agent instructions for this repo
```

## Documentation

* **[`CONTEXT.md`](CONTEXT.md)** — the domain glossary. Start here for the precise meaning of *Topic*, *Decision anchor*, *Check*, *Evidence*, *Receipt*, *Worklist*, *Coach*, and how they relate.
* **[`docs/planning/product.md`](docs/planning/product.md)** — the canonical product spec (what Ledger *is* and what gets demoed).
* **[`docs/adr/`](docs/adr/)** — architecture decisions:

  * [0001](docs/adr/0001-dual-provider-ingestion-claude-native-spine.md) — dual-provider ingestion, Claude-native spine *(superseded by 0004)*
  * [0002](docs/adr/0002-agentic-topic-discovery-deterministic-verification.md) — agentic topic discovery, deterministic verification
  * [0003](docs/adr/0003-idempotent-worklist-reconciliation.md) — idempotent worklist reconciliation over an append-only ledger
  * [0004](docs/adr/0004-drop-codex-single-provider-selectable-coach-model.md) — drop Codex; single-provider Claude-native, selectable coach model
* **[`docs/agents/`](docs/agents/)** — conventions for agents working in this repo (issue tracker, triage labels, domain docs).

## Status

Built for the UC Berkeley AI Hackathon Anthropic track. The prototype includes one real Git project, several ranked topics, one fully-grounded hero topic/check, and a persisted practice history. The longitudinal/decay and cross-project-learning stories are narrated, not yet built — see the Roadmap section of `docs/planning/product.md`.

## License

[MIT](LICENSE) © 2026 Ledger contributors
