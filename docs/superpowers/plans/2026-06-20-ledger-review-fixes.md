# Ledger Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the current Ledger branch into a coherent, reviewable vertical slice that matches the hackathon demo contract: persistent revision-specific ownership history, installable metadata, a working test UI, and committed source without generated artifacts.

**Architecture:** Keep the backend Python-first and local-first. Extend the existing SQLite repository layer with topic revision and completion history tables, expose that data through the existing FastAPI endpoints, and keep the frontend as a thin tester over real backend state. Do not add automatic topic generation, arbitrary repo sandboxing, daemon install, auth, cloud sync, or production deployment.

**Tech Stack:** FastAPI, stdlib `sqlite3`, pytest, React + Vite, local CLI coaches (`claude -p` and `codex exec -`).

---

## Verified Review Status

- Finding 1 is valid: the schema does not yet model `topic_revisions`, `reflections`, or practice history rich enough for the docs.
- Finding 2 is partially incorrect: `httpx2` is not a typo in this environment; Starlette's current `TestClient` explicitly asked for `httpx2`. The fix is to verify fresh installability and pin intentionally.
- Finding 3 is stale: `frontend/` now exists and builds, but it still needs cleanup, API polish, and committed metadata.
- Finding 4 is valid: source is uncommitted, and generated artifacts such as `node_modules`, `dist`, `__pycache__`, `.pytest_cache`, `.venv`, and egg-info must be ignored or removed from the working tree.

## File Structure

- Modify `app/ledger_backend/db.py`: add revision, reflection, and practice-history tables.
- Modify `app/ledger_backend/repository.py`: seed topic revisions, attach checks to revisions, persist completion summaries.
- Modify `app/ledger_backend/api.py`: include revision/history data on topic/check responses.
- Modify `tests/test_repository.py`: cover revision-specific check completion and history.
- Modify `tests/test_api.py`: cover API exposure of practice history.
- Modify `tests/test_coach.py`: keep Claude/Codex CLI provider coverage.
- Modify `frontend/src/main.jsx`: render practice history and use explicit coach providers.
- Modify `frontend/src/styles.css`: style practice history and provider selector.
- Modify `pyproject.toml`: keep package metadata installable and document `httpx2` by test coverage.
- Create `.gitignore`: exclude generated Python/Node/build/runtime artifacts.
- Modify `README.md`: add run commands for backend, frontend, and tests.

---

### Task 1: Ignore Generated Artifacts

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Add `.gitignore`**

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
*.egg-info/
node_modules/
dist/
.DS_Store
```

- [ ] **Step 2: Remove generated files from the working tree**

Run:

```bash
cd /home/dhn/ledger
find app tests -type d -name __pycache__ -prune -exec rm -rf {} +
rm -rf .pytest_cache app/*.egg-info ledger.egg-info frontend/node_modules frontend/dist
```

Expected: `git status --short` shows source files only, not caches or installed dependencies.

- [ ] **Step 3: Commit cleanup**

```bash
git add .gitignore
git commit -m "chore: ignore generated artifacts"
```

Expected: commit succeeds on `codex/backend-core`.

---

### Task 2: Add Revision-Specific Persistence

**Files:**
- Modify: `app/ledger_backend/db.py`
- Modify: `app/ledger_backend/repository.py`
- Test: `tests/test_repository.py`

- [ ] **Step 1: Write failing repository test**

Add to `tests/test_repository.py`:

```python
def test_topic_includes_revision_and_practice_history(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    topic = repo.get_topic("tenant-cache-isolation")
    assert topic["current_revision"]["id"] == "tenant-cache-isolation-r1"
    assert topic["practice_history"] == []

    check = repo.create_check("tenant-cache-isolation")
    file_state = repo.read_check_file(check["id"], "retrieval/rerank.py")
    fixed = file_state["content"].replace(
        "return list(documents)",
        "return [doc for doc in documents if doc.tenant_id == tenant_id]",
    )
    repo.update_check_file(check["id"], "retrieval/rerank.py", fixed)
    repo.run_check(check["id"])
    repo.complete_check(check["id"], reflection={
        "invariant": "Documents must be scoped by tenant_id.",
        "rationale": "Tenant data must not leak across retrieval results.",
        "future_risk": "Caching or batching can accidentally omit tenant identity.",
    })

    topic = repo.get_topic("tenant-cache-isolation")
    assert topic["practice_history"][0]["revision_id"] == "tenant-cache-isolation-r1"
    assert topic["practice_history"][0]["reflection"]["invariant"].startswith("Documents")
```

- [ ] **Step 2: Verify test fails**

Run:

```bash
cd /home/dhn/ledger
.venv/bin/python -m pytest tests/test_repository.py::test_topic_includes_revision_and_practice_history -q
```

Expected: FAIL because `current_revision`, `practice_history`, and reflection-aware `complete_check` do not exist.

- [ ] **Step 3: Extend schema**

Add tables to `app/ledger_backend/db.py`:

```sql
CREATE TABLE IF NOT EXISTS topic_revisions (
    id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL REFERENCES topics(id),
    revision INTEGER NOT NULL,
    commit_sha TEXT NOT NULL,
    invariant TEXT NOT NULL,
    risk TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id TEXT NOT NULL REFERENCES checks(id),
    invariant TEXT NOT NULL,
    rationale TEXT NOT NULL,
    future_risk TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Add `revision_id TEXT REFERENCES topic_revisions(id)` to `checks`.

- [ ] **Step 4: Seed revision data**

In `LedgerRepository._seed`, insert a `topic_revisions` row for `tenant-cache-isolation`:

```python
conn.execute(
    """
    INSERT INTO topic_revisions
    (id, topic_id, revision, commit_sha, invariant, risk, fingerprint)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
    (
        "tenant-cache-isolation-r1",
        "tenant-cache-isolation",
        1,
        "demo-seed",
        "Documents visible to a request must match the active tenant_id.",
        "Tenant data leakage through retrieval caching.",
        "retrieval.visible_documents_for_tenant:v1",
    ),
)
```

- [ ] **Step 5: Attach checks to current revision**

In `create_check`, look up the newest revision for the topic and insert `revision_id` into `checks`.

- [ ] **Step 6: Persist reflection on completion**

Change `complete_check` to accept optional `reflection: dict[str, str] | None`, and insert into `reflections` when provided.

- [ ] **Step 7: Include revision and history in `get_topic`**

Return:

```python
payload["current_revision"] = dict(current_revision)
payload["practice_history"] = [
    {
        "check_id": row["check_id"],
        "revision_id": row["revision_id"],
        "run_count": row["run_count"],
        "passed": bool(row["passed"]),
        "completed_at": row["completed_at"],
        "reflection": {...} or None,
    }
]
```

- [ ] **Step 8: Verify repository test passes**

Run:

```bash
.venv/bin/python -m pytest tests/test_repository.py -q
```

Expected: all repository tests pass.

- [ ] **Step 9: Commit persistence model**

```bash
git add app/ledger_backend/db.py app/ledger_backend/repository.py tests/test_repository.py
git commit -m "feat: persist topic revisions and practice history"
```

---

### Task 3: Expose History Through the API

**Files:**
- Modify: `app/ledger_backend/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing API test**

Add to `tests/test_api.py`:

```python
def test_api_topic_response_includes_revision_and_practice_history(tmp_path):
    app = create_app(db_path=tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    client = TestClient(app)

    topic = client.get("/api/topics/tenant-cache-isolation")

    assert topic.status_code == 200
    body = topic.json()
    assert body["current_revision"]["id"] == "tenant-cache-isolation-r1"
    assert body["practice_history"] == []
```

- [ ] **Step 2: Verify test fails before repository work is complete**

Run:

```bash
.venv/bin/python -m pytest tests/test_api.py::test_api_topic_response_includes_revision_and_practice_history -q
```

Expected before Task 2 implementation: FAIL on missing keys. Expected after Task 2: PASS without changing route shape.

- [ ] **Step 3: Add reflection request shape**

In `app/ledger_backend/api.py`, define:

```python
class ReflectionRequest(BaseModel):
    invariant: str
    rationale: str
    future_risk: str
```

Change `complete_check` route to accept `payload: ReflectionRequest | None = None` and pass `payload.model_dump()` when present.

- [ ] **Step 4: Verify API suite passes**

Run:

```bash
.venv/bin/python -m pytest tests/test_api.py -q
```

Expected: API tests pass.

- [ ] **Step 5: Commit API history exposure**

```bash
git add app/ledger_backend/api.py tests/test_api.py
git commit -m "feat: expose ownership history through api"
```

---

### Task 4: Frontend History and Provider UI

**Files:**
- Modify: `frontend/src/main.jsx`
- Modify: `frontend/src/styles.css`
- Verify: `frontend/package.json`

- [ ] **Step 1: Render revision metadata**

In topic detail, display `selectedTopic.current_revision.invariant` and `selectedTopic.current_revision.risk` when present.

- [ ] **Step 2: Render practice history**

Below evidence cards, render `selectedTopic.practice_history` as rows with completion time, revision ID, run count, pass/fail, and reflection fields.

- [ ] **Step 3: Send reflection on completion**

For the current tester UI, use a lightweight default reflection payload when `runResult.passed` is true:

```js
const reflection = {
  invariant: "Documents must remain scoped to the active tenant.",
  rationale: "Cross-tenant retrieval is a data leak.",
  future_risk: "Caching or batching can omit tenant identity."
};
await api(`/api/checks/${check.id}/complete`, {
  method: "POST",
  body: JSON.stringify(reflection)
});
```

- [ ] **Step 4: Keep explicit provider labels**

Ensure the dropdown still sends `claude-code` and `codex-exec`, matching backend aliases.

- [ ] **Step 5: Build frontend**

Run:

```bash
cd /home/dhn/ledger/frontend
npm run build
```

Expected: Vite build succeeds.

- [ ] **Step 6: Commit frontend tester updates**

```bash
git add frontend/src/main.jsx frontend/src/styles.css frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/index.html
git commit -m "feat: show ownership history in test ui"
```

---

### Task 5: Fresh Setup Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write setup docs**

Replace the stub README with:

```markdown
# Ledger

Local-first ownership checks for AI-assisted code.

## Backend

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/uvicorn ledger_backend.api:app --host 0.0.0.0 --port 4317
```

## Frontend

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Open `http://100.68.145.17:5173/` on the ASUS Tailscale network.

## Coach Providers

Ledger uses local CLI auth rather than direct API keys.

- Claude Code: `claude -p`
- Codex: `codex exec -`
```

- [ ] **Step 2: Verify fresh backend install**

Run outside the existing `.venv` if possible:

```bash
python3 -m venv /tmp/ledger-fresh-venv
/tmp/ledger-fresh-venv/bin/python -m pip install -e '.[dev]'
/tmp/ledger-fresh-venv/bin/python -m pytest -q
```

Expected: all tests pass. If installation fails on `httpx2`, keep `httpx2` only if Starlette still requires it; otherwise switch tests to a compatible `httpx` version and update `pyproject.toml`.

- [ ] **Step 3: Verify frontend fresh install**

Run:

```bash
cd frontend
rm -rf node_modules dist
npm ci
npm run build
```

Expected: install and build pass from `package-lock.json`.

- [ ] **Step 4: Commit setup docs**

```bash
git add README.md pyproject.toml frontend/package.json frontend/package-lock.json
git commit -m "docs: add local setup instructions"
```

---

### Task 6: Final Branch Hygiene

**Files:**
- All source files created in the backend/frontend slice.

- [ ] **Step 1: Run final verification**

```bash
cd /home/dhn/ledger
.venv/bin/python -m pytest -q
cd frontend
npm run build
```

Expected: all backend tests pass and frontend build succeeds.

- [ ] **Step 2: Inspect status**

```bash
git status --short
```

Expected: no generated artifacts. Only intentional source files should be staged or committed.

- [ ] **Step 3: Push branch**

```bash
git push -u origin codex/backend-core
```

Expected: branch is available on GitHub.

- [ ] **Step 4: Open draft PR**

```bash
gh pr create --draft --fill --head codex/backend-core
```

Expected: draft PR summarizes backend vertical slice, test UI, and known out-of-scope items.

---

## Self-Review

- Spec coverage: The plan covers richer persistence, installability, frontend presence, and commit hygiene. It intentionally does not add automatic topic generation, daemon hooks, arbitrary repo sandboxing, cloud sync, or production auth because the build plan excludes those from the 24-hour slice.
- Placeholder scan: No TBD/TODO placeholders remain.
- Type consistency: `revision_id`, `current_revision`, `practice_history`, and `reflection` names are used consistently across repository, API, and frontend tasks.

