# Check Difficulty Plans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real `easy`, `medium`, and `hard` check modes where easy is multiple-choice only, medium is a planned mix of multiple-choice plus sandbox, and hard remains the current sandbox workflow with hints and coach.

**Architecture:** The backend owns exercise plans. A check stores a concrete `plan_json` snapshot generated from a small Python template registry; the frontend renders that plan without knowing correct answers. The first vertical slice supports the hero topic only, but the data model and API are real enough to extend to additional topics.

**Tech Stack:** FastAPI, SQLite, Python repository layer, React/Vite TypeScript frontend, pytest, `npm run build`.

---

## File Structure

- Create `backend/exercise_templates.py`: typed template registry, public-plan stripping, answer validation.
- Modify `backend/db.py`: add `difficulty`, `template_id`, and `plan_json` columns to `checks`; add `check_answers`.
- Modify `backend/repository.py`: create checks from templates, expose public plan, validate answers.
- Modify `backend/api.py`: accept difficulty on check creation and expose answer submission.
- Modify `backend/tests/test_backend_contract.py`: backend contract tests for all three difficulty modes and answer validation.
- Modify `frontend/src/api.ts`: add difficulty, plan, question, and answer types.
- Modify `frontend/src/App.tsx`: pass difficulty into check creation and track answer results.
- Modify `frontend/src/screens/Topic.tsx`: expose difficulty launch buttons.
- Modify `frontend/src/screens/Workspace.tsx`: render plan steps; easy hides editor, medium gates editor after MC answers, hard remains current editor.

---

### Task 1: Backend Template Registry

**Files:**
- Create: `backend/exercise_templates.py`
- Test: `backend/tests/test_backend_contract.py`

- [ ] **Step 1: Write failing tests for public plans and validation**

Add these tests to `backend/tests/test_backend_contract.py`:

```python
def test_easy_check_returns_multiple_choice_only_plan(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    check = repo.create_check("tenant-cache-isolation", difficulty="easy")

    assert check["difficulty"] == "easy"
    assert check["template_id"] == "tenant-cache-easy"
    assert [step["type"] for step in check["plan"]["steps"]] == ["multiple_choice", "multiple_choice"]
    assert "correct_index" not in str(check["plan"])
    assert check["plan"]["questions"][0]["kind"] == "concept"
    assert check["plan"]["questions"][1]["kind"] == "debugging"


def test_medium_check_returns_question_then_sandbox_plan(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    check = repo.create_check("tenant-cache-isolation", difficulty="medium")

    assert check["difficulty"] == "medium"
    assert check["template_id"] == "tenant-cache-medium"
    assert [step["type"] for step in check["plan"]["steps"]] == ["multiple_choice", "sandbox"]


def test_hard_check_keeps_current_sandbox_plan(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    check = repo.create_check("tenant-cache-isolation", difficulty="hard")

    assert check["difficulty"] == "hard"
    assert check["template_id"] == "tenant-cache-hard"
    assert [step["type"] for step in check["plan"]["steps"]] == ["sandbox"]
    assert check["target_file"] == "retrieval/rerank.py"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
./.venv/bin/python -m pytest -q backend/tests/test_backend_contract.py::test_easy_check_returns_multiple_choice_only_plan backend/tests/test_backend_contract.py::test_medium_check_returns_question_then_sandbox_plan backend/tests/test_backend_contract.py::test_hard_check_keeps_current_sandbox_plan
```

Expected: fail because `create_check` does not accept `difficulty` and no `plan` exists.

- [ ] **Step 3: Add template registry**

Create `backend/exercise_templates.py`:

```python
from __future__ import annotations

from copy import deepcopy
from typing import Any


Difficulty = str

VALID_DIFFICULTIES = {"easy", "medium", "hard"}


HERO_TEMPLATES: dict[str, dict[str, Any]] = {
    "easy": {
        "template_id": "tenant-cache-easy",
        "difficulty": "easy",
        "steps": [
            {"type": "multiple_choice", "question_id": "tenant-filter-purpose"},
            {"type": "multiple_choice", "question_id": "tenant-filter-debug"},
        ],
        "questions": [
            {
                "id": "tenant-filter-purpose",
                "kind": "concept",
                "prompt": "What should this function guarantee before ranking or returning documents?",
                "choices": [
                    "Only documents for the requested tenant are returned.",
                    "All documents are returned so the caller has more context.",
                    "Documents are grouped by score before tenant filtering.",
                ],
                "correct_index": 0,
                "rationale": "The invariant is tenant isolation: documents from other tenants must not be visible.",
            },
            {
                "id": "tenant-filter-debug",
                "kind": "debugging",
                "prompt": "Which solution best fixes the failing behavior?",
                "choices": [
                    "Return only documents whose tenant_id matches the requested tenant_id.",
                    "Return all documents and rely on a later caller to filter.",
                    "Sort documents by score and return the highest scoring documents.",
                ],
                "correct_index": 0,
                "rationale": "The failing test proves the function must filter by tenant before returning results.",
            },
        ],
    },
    "medium": {
        "template_id": "tenant-cache-medium",
        "difficulty": "medium",
        "steps": [
            {"type": "multiple_choice", "question_id": "tenant-filter-purpose"},
            {"type": "sandbox"},
        ],
        "questions": [
            {
                "id": "tenant-filter-purpose",
                "kind": "concept",
                "prompt": "What property should you preserve while fixing the failing test?",
                "choices": [
                    "Tenant isolation: only the requested tenant's documents should be returned.",
                    "Score ordering: every document should be returned in descending score order.",
                    "Object identity: the returned list should contain the original input list object.",
                ],
                "correct_index": 0,
                "rationale": "The check is about tenant isolation, not ranking or object identity.",
            }
        ],
    },
    "hard": {
        "template_id": "tenant-cache-hard",
        "difficulty": "hard",
        "steps": [{"type": "sandbox"}],
        "questions": [],
    },
}


def template_for(topic_id: str, difficulty: str | None) -> dict[str, Any]:
    selected = (difficulty or "hard").lower()
    if selected not in VALID_DIFFICULTIES:
        raise ValueError(f"unsupported difficulty: {selected}")
    if topic_id != "tenant-cache-isolation":
        selected = "hard"
    return deepcopy(HERO_TEMPLATES[selected])


def public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    safe = deepcopy(plan)
    for question in safe.get("questions", []):
        question.pop("correct_index", None)
        question.pop("rationale", None)
    return safe


def validate_answers(plan: dict[str, Any], answers: dict[str, int]) -> dict[str, Any]:
    results = []
    questions = {question["id"]: question for question in plan.get("questions", [])}
    for question_id, selected_index in answers.items():
        question = questions.get(question_id)
        if question is None:
            results.append(
                {
                    "question_id": question_id,
                    "selected_index": selected_index,
                    "correct": False,
                    "rationale": "This question is not part of the current check.",
                }
            )
            continue
        correct = selected_index == question["correct_index"]
        results.append(
            {
                "question_id": question_id,
                "selected_index": selected_index,
                "correct": correct,
                "rationale": question["rationale"],
            }
        )
    expected_ids = {question["id"] for question in plan.get("questions", [])}
    answered_ids = set(answers)
    missing = expected_ids - answered_ids
    for question_id in sorted(missing):
        question = questions[question_id]
        results.append(
            {
                "question_id": question_id,
                "selected_index": None,
                "correct": False,
                "rationale": question["rationale"],
            }
        )
    return {"passed": bool(results) and all(item["correct"] for item in results), "results": results}
```

- [ ] **Step 4: Do not wire repository yet**

Run:

```bash
./.venv/bin/python -m pytest -q backend/tests/test_backend_contract.py::test_easy_check_returns_multiple_choice_only_plan
```

Expected: still fails because repository does not use templates yet.

- [ ] **Step 5: Commit**

```bash
git add backend/exercise_templates.py backend/tests/test_backend_contract.py
git commit -m "test: define check difficulty plan contract"
```

---

### Task 2: Persist Difficulty And Plan Snapshot

**Files:**
- Modify: `backend/db.py`
- Modify: `backend/repository.py`
- Test: `backend/tests/test_backend_contract.py`

- [ ] **Step 1: Add schema migration**

Modify `backend/db.py`.

In `CREATE TABLE IF NOT EXISTS checks`, add:

```sql
    difficulty TEXT NOT NULL DEFAULT 'hard',
    template_id TEXT NOT NULL DEFAULT 'tenant-cache-hard',
    plan_json TEXT NOT NULL DEFAULT '{"difficulty":"hard","template_id":"tenant-cache-hard","steps":[{"type":"sandbox"}],"questions":[]}',
```

Place those columns after `test_command TEXT NOT NULL,`.

Add these statements to `MIGRATIONS`:

```python
"ALTER TABLE checks ADD COLUMN difficulty TEXT NOT NULL DEFAULT 'hard'",
"ALTER TABLE checks ADD COLUMN template_id TEXT NOT NULL DEFAULT 'tenant-cache-hard'",
"ALTER TABLE checks ADD COLUMN plan_json TEXT NOT NULL DEFAULT '{\"difficulty\":\"hard\",\"template_id\":\"tenant-cache-hard\",\"steps\":[{\"type\":\"sandbox\"}],\"questions\":[]}'",
```

- [ ] **Step 2: Wire repository create/get check**

Modify imports in `backend/repository.py`:

```python
from .exercise_templates import public_plan, template_for
```

Change the method signature:

```python
def create_check(self, topic_id: str, difficulty: str | None = None) -> dict[str, Any]:
```

Inside `create_check`, after `check_id`:

```python
template = template_for(topic_id, difficulty)
```

Change the insert statement:

```python
conn.execute(
    """
    INSERT INTO checks
    (id, topic_id, topic_revision_id, state, sandbox_path, target_file, test_command, difficulty, template_id, plan_json)
    VALUES (?, ?, ?, 'in_progress', ?, 'retrieval/rerank.py', 'python -m pytest -s tests', ?, ?, ?)
    """,
    (
        check_id,
        topic_id,
        revision["id"],
        str(sandbox_path),
        template["difficulty"],
        template["template_id"],
        json.dumps(template, sort_keys=True),
    ),
)
```

In `get_check`, after `payload = dict(check)`:

```python
plan = json.loads(payload.get("plan_json") or "{}")
payload["plan"] = public_plan(plan)
payload.pop("plan_json", None)
```

- [ ] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m pytest -q backend/tests/test_backend_contract.py::test_easy_check_returns_multiple_choice_only_plan backend/tests/test_backend_contract.py::test_medium_check_returns_question_then_sandbox_plan backend/tests/test_backend_contract.py::test_hard_check_keeps_current_sandbox_plan
```

Expected: pass.

- [ ] **Step 4: Run wider backend tests**

Run:

```bash
./.venv/bin/python -m pytest -q backend/tests/test_backend_contract.py backend/tests/test_repository.py
```

Expected: pass. If a test asserts `test_command == "python -m pytest tests"`, update expected value to `"python -m pytest -s tests"` because stdout is intentionally visible for print probes.

- [ ] **Step 5: Commit**

```bash
git add backend/db.py backend/repository.py backend/tests/test_backend_contract.py
git commit -m "feat: persist check difficulty plans"
```

---

### Task 3: Answer Submission API

**Files:**
- Modify: `backend/db.py`
- Modify: `backend/repository.py`
- Modify: `backend/api.py`
- Test: `backend/tests/test_backend_contract.py`

- [ ] **Step 1: Add failing answer validation tests**

Add to `backend/tests/test_backend_contract.py`:

```python
def test_submit_check_answers_validates_easy_mode_server_side(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()
    check = repo.create_check("tenant-cache-isolation", difficulty="easy")

    result = repo.submit_check_answers(
        check["id"],
        {
            "tenant-filter-purpose": 0,
            "tenant-filter-debug": 0,
        },
    )

    assert result["passed"] is True
    assert all(item["correct"] for item in result["results"])
    assert "tenant isolation" in result["results"][0]["rationale"].lower()


def test_submit_check_answers_records_wrong_answer(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()
    check = repo.create_check("tenant-cache-isolation", difficulty="easy")

    result = repo.submit_check_answers(check["id"], {"tenant-filter-purpose": 1, "tenant-filter-debug": 0})

    assert result["passed"] is False
    assert result["results"][0]["correct"] is False
    assert result["results"][0]["selected_index"] == 1
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
./.venv/bin/python -m pytest -q backend/tests/test_backend_contract.py::test_submit_check_answers_validates_easy_mode_server_side backend/tests/test_backend_contract.py::test_submit_check_answers_records_wrong_answer
```

Expected: fail because `submit_check_answers` does not exist.

- [ ] **Step 3: Add `check_answers` table**

Modify `backend/db.py` and add after `attempts`:

```sql
CREATE TABLE IF NOT EXISTS check_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id TEXT NOT NULL REFERENCES checks(id),
    question_id TEXT NOT NULL,
    selected_index INTEGER,
    correct INTEGER NOT NULL,
    rationale TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] **Step 4: Implement repository validation**

Modify imports in `backend/repository.py`:

```python
from .exercise_templates import public_plan, template_for, validate_answers
```

Add method near `pseudocode_comments`:

```python
def submit_check_answers(self, check_id: str, answers: dict[str, int]) -> dict[str, Any]:
    check = self.get_check(check_id)
    with connect(self.db_path) as conn:
        row = conn.execute("SELECT plan_json FROM checks WHERE id = ?", (check_id,)).fetchone()
        if not row:
            raise KeyError(check_id)
        plan = json.loads(row["plan_json"])
        result = validate_answers(plan, answers)
        conn.executemany(
            """
            INSERT INTO check_answers (check_id, question_id, selected_index, correct, rationale)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    check_id,
                    item["question_id"],
                    item["selected_index"],
                    int(item["correct"]),
                    item["rationale"],
                )
                for item in result["results"]
            ],
        )
        if result["passed"] and check["difficulty"] == "easy":
            conn.execute(
                "UPDATE checks SET state = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (check_id,),
            )
        conn.commit()
    return result
```

- [ ] **Step 5: Add API model and route**

Modify `backend/api.py`.

Add model:

```python
class AnswerRequest(BaseModel):
    answers: dict[str, int]
```

Add route before `/api/checks/{check_id}/files/{file_path:path}`:

```python
@app.post("/api/checks/{check_id}/answers")
def submit_answers(check_id: str, payload: AnswerRequest) -> dict:
    try:
        return repo.submit_check_answers(check_id, payload.answers)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="check not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 6: Add route registry assertion**

In `test_contract_alias_routes_are_registered`, add:

```python
assert "/api/checks/{check_id}/answers" in paths
```

- [ ] **Step 7: Run tests**

Run:

```bash
./.venv/bin/python -m pytest -q backend/tests/test_backend_contract.py backend/tests/test_repository.py
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add backend/db.py backend/repository.py backend/api.py backend/tests/test_backend_contract.py
git commit -m "feat: validate multiple choice check answers"
```

---

### Task 4: API Types And Check Creation Difficulty

**Files:**
- Modify: `backend/api.py`
- Modify: `frontend/src/api.ts`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Update backend check request**

Modify `backend/api.py`:

```python
class CheckRequest(BaseModel):
    topic_id: str | None = None
    difficulty: str | None = None
```

Change alias route:

```python
@app.post("/api/checks")
def create_check_alias(payload: CheckRequest) -> dict:
    if not payload.topic_id:
        raise HTTPException(status_code=400, detail="topic_id is required")
    try:
        return repo.create_check(payload.topic_id, difficulty=payload.difficulty)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="topic not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

Change topic route:

```python
@app.post("/api/topics/{topic_id}/checks")
def create_check(topic_id: str, payload: CheckRequest | None = None) -> dict:
    try:
        return repo.create_check(topic_id, difficulty=payload.difficulty if payload else None)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="topic not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 2: Add API test**

Add to `backend/tests/test_api.py`:

```python
def test_api_creates_easy_check_with_public_plan(tmp_path):
    app = create_app(db_path=tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    client = TestClient(app)
    topic_id = client.get("/api/projects/docs-api/topics").json()[0]["id"]

    response = client.post(f"/api/topics/{topic_id}/checks", json={"difficulty": "easy"})

    assert response.status_code == 200
    body = response.json()
    assert body["difficulty"] == "easy"
    assert body["plan"]["steps"][0]["type"] == "multiple_choice"
    assert "correct_index" not in str(body["plan"])
```

- [ ] **Step 3: Run API test**

Run:

```bash
./.venv/bin/python -m pytest -q backend/tests/test_api.py::test_api_creates_easy_check_with_public_plan
```

Expected: pass. If TestClient hangs in this environment, run repository tests as the source of truth and verify route registration in contract tests.

- [ ] **Step 4: Update frontend API types**

Modify `frontend/src/api.ts`:

```ts
export type Difficulty = 'easy' | 'medium' | 'hard'

export interface ExerciseQuestion {
  id: string
  kind: 'concept' | 'debugging'
  prompt: string
  choices: string[]
}

export interface ExerciseStep {
  type: 'multiple_choice' | 'sandbox'
  question_id?: string
}

export interface ExercisePlan {
  difficulty: Difficulty
  template_id: string
  steps: ExerciseStep[]
  questions: ExerciseQuestion[]
}
```

Extend `Check`:

```ts
export interface Check {
  id: string
  topic_id: string
  target_file: string
  test_command: string
  difficulty: Difficulty
  template_id: string
  plan: ExercisePlan
}
```

Change `createCheck`:

```ts
export const createCheck = (topicId: string, difficulty: Difficulty = 'hard') =>
  req<Check>(`/api/topics/${cid(topicId)}/checks`, { method: 'POST', body: { difficulty } })
```

Add answer types:

```ts
export interface AnswerResult {
  question_id: string
  selected_index: number | null
  correct: boolean
  rationale: string
}

export interface SubmitAnswersResponse {
  passed: boolean
  results: AnswerResult[]
}

export const submitAnswers = (checkId: string, answers: Record<string, number>) =>
  req<SubmitAnswersResponse>(`/api/checks/${cid(checkId)}/answers`, { method: 'POST', body: { answers } })
```

- [ ] **Step 5: Run frontend typecheck**

Run:

```bash
npm run build
```

Expected: fail until `App.tsx` is updated in Task 5 because `createCheck` signature changed only compatibly, so it may pass.

- [ ] **Step 6: Commit**

```bash
git add backend/api.py backend/tests/test_api.py frontend/src/api.ts
git commit -m "feat: expose difficulty plans through API"
```

---

### Task 5: Difficulty Launch UI

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/screens/Topic.tsx`
- Build: `frontend`

- [ ] **Step 1: Update Topic props**

In `frontend/src/screens/Topic.tsx`, change the prop:

```ts
onStartCheck: (difficulty: api.Difficulty) => void
```

Import API types:

```ts
import * as api from '../api'
```

Replace the single start button with three buttons:

```tsx
<div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
  {[
    { difficulty: 'easy' as api.Difficulty, label: 'Easy: multiple choice' },
    { difficulty: 'medium' as api.Difficulty, label: 'Medium: guided debug' },
    { difficulty: 'hard' as api.Difficulty, label: 'Hard: sandbox' },
  ].map((item) => (
    <button
      key={item.difficulty}
      onClick={() => onStartCheck(item.difficulty)}
      style={{
        background: item.difficulty === 'hard' ? 'var(--accent)' : 'var(--panel2)',
        color: item.difficulty === 'hard' ? '#1c140f' : 'var(--tx)',
        border: '1px solid var(--bd2)',
        borderRadius: 9,
        padding: '10px 14px',
        fontFamily: "'Geist', sans-serif",
        fontSize: 13,
        fontWeight: 600,
        cursor: 'pointer',
      }}
    >
      {item.label}
    </button>
  ))}
</div>
```

- [ ] **Step 2: Update App startCheck**

In `frontend/src/App.tsx`, change:

```ts
const startCheck = useCallback(async (difficulty: api.Difficulty = 'hard') => {
```

Change create call:

```ts
const created = await api.createCheck(topicDetail.id, difficulty)
```

Update `Topic` usage:

```tsx
onStartCheck={startCheck}
```

- [ ] **Step 3: Run build**

Run:

```bash
npm run build
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/screens/Topic.tsx
git commit -m "feat: launch checks by difficulty"
```

---

### Task 6: Frontend Plan Renderer

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/screens/Workspace.tsx`
- Build: `frontend`

- [ ] **Step 1: Add answer state in App**

In `frontend/src/App.tsx`, add:

```ts
const [answers, setAnswers] = useState<Record<string, number>>({})
const [answerResults, setAnswerResults] = useState<api.AnswerResult[]>([])
```

Reset in `startCheck`:

```ts
setAnswers({})
setAnswerResults([])
```

Add submit handler:

```ts
const submitAnswers = useCallback(async () => {
  if (!check) return
  try {
    const result = await api.submitAnswers(check.id, answers)
    setAnswerResults(result.results)
    if (result.passed && check.difficulty === 'easy') {
      setPhase('pass')
    }
  } catch (e) {
    setRunOutput(`Could not submit answers: ${e instanceof Error ? e.message : String(e)}`)
    setPhase('error')
  }
}, [check, answers])
```

Pass to `Workspace`:

```tsx
answers={answers}
answerResults={answerResults}
onAnswer={(questionId, choiceIndex) => setAnswers((current) => ({ ...current, [questionId]: choiceIndex }))}
submitAnswers={submitAnswers}
```

- [ ] **Step 2: Add Workspace props**

In `frontend/src/screens/Workspace.tsx`:

```ts
answers: Record<string, number>
answerResults: api.AnswerResult[]
onAnswer: (questionId: string, choiceIndex: number) => void
submitAnswers: () => void
```

- [ ] **Step 3: Render multiple-choice panel**

Add near the top of `Workspace` after derived constants:

```ts
const plan = check?.plan
const questionsById = new Map((plan?.questions || []).map((q) => [q.id, q]))
const mcSteps = (plan?.steps || []).filter((step) => step.type === 'multiple_choice')
const hasSandboxStep = (plan?.steps || []).some((step) => step.type === 'sandbox')
const allMcAnswered = mcSteps.every((step) => step.question_id && answers[step.question_id] !== undefined)
const canShowSandbox = !plan || check?.difficulty === 'hard' || (hasSandboxStep && (check?.difficulty === 'medium' ? answerResults.length > 0 : false))
const easyMode = check?.difficulty === 'easy'
```

Add a question card component inside `Workspace` before the editor area:

```tsx
const questionPanel = mcSteps.length > 0 && (
  <div className="lg-scroll" style={{ flex: easyMode ? 1 : 'none', maxHeight: easyMode ? undefined : 210, overflow: 'auto', borderBottom: '1px solid var(--bd)', background: 'var(--panel)', padding: 16 }}>
    <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 10 }}>
      {check?.difficulty} check
    </div>
    {mcSteps.map((step) => {
      const q = step.question_id ? questionsById.get(step.question_id) : undefined
      if (!q) return null
      const result = answerResults.find((item) => item.question_id === q.id)
      return (
        <div key={q.id} style={{ border: '1px solid var(--bd2)', borderRadius: 10, padding: 13, marginBottom: 10, background: 'var(--bg)' }}>
          <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 9 }}>{q.prompt}</div>
          {q.choices.map((choice, index) => {
            const selected = answers[q.id] === index
            return (
              <button
                key={choice}
                onClick={() => onAnswer(q.id, index)}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  marginTop: 6,
                  padding: '8px 10px',
                  borderRadius: 8,
                  border: `1px solid ${selected ? 'var(--accent)' : 'var(--bd2)'}`,
                  background: selected ? 'rgba(200,116,77,0.12)' : 'var(--panel2)',
                  color: 'var(--tx)',
                  cursor: 'pointer',
                }}
              >
                {choice}
              </button>
            )
          })}
          {result && (
            <div style={{ marginTop: 9, color: result.correct ? 'var(--green)' : 'var(--red)', fontSize: 12.5, lineHeight: 1.45 }}>
              {result.correct ? 'Correct. ' : 'Not quite. '}
              <span style={{ color: 'var(--mut)' }}>{result.rationale}</span>
            </div>
          )}
        </div>
      )
    })}
    <button
      onClick={submitAnswers}
      disabled={!allMcAnswered}
      style={{
        background: allMcAnswered ? 'var(--accent)' : 'rgba(200,116,77,0.35)',
        color: '#1c140f',
        border: 'none',
        borderRadius: 8,
        padding: '9px 14px',
        fontWeight: 600,
        cursor: allMcAnswered ? 'pointer' : 'default',
      }}
    >
      Check answers
    </button>
  </div>
)
```

- [ ] **Step 4: Gate editor by plan**

Inside the sandbox column, render:

```tsx
{questionPanel}
{!canShowSandbox && !easyMode && (
  <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--mut)', fontFamily: mono, fontSize: 12 }}>
    Answer the guided question to unlock the sandbox.
  </div>
)}
{easyMode && (
  <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--mut)', fontFamily: mono, fontSize: 12 }}>
    Easy mode is multiple-choice only.
  </div>
)}
{canShowSandbox && !easyMode && (
  <>
    existing editor, run bar, and output JSX
  </>
)}
```

When implementing, move the existing editor/run/output JSX into the final fragment rather than duplicating it.

- [ ] **Step 5: Disable pseudocode button outside sandbox**

Only render `Add pseudocode hints` when:

```tsx
editable && canShowSandbox && !easyMode
```

- [ ] **Step 6: Completion behavior**

Change `canComplete` in `App.tsx`:

```tsx
canComplete={phase === 'pass' || (check?.difficulty === 'easy' && answerResults.length > 0 && answerResults.every((item) => item.correct))}
```

- [ ] **Step 7: Run build**

Run:

```bash
npm run build
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.tsx frontend/src/screens/Workspace.tsx
git commit -m "feat: render exercise plan steps"
```

---

### Task 7: End-To-End Verification And Push

**Files:**
- Verify only unless failures require fixes.

- [ ] **Step 1: Run backend tests**

Run:

```bash
./.venv/bin/python -m pytest -q backend/tests/test_backend_contract.py backend/tests/test_repository.py backend/tests/test_coach.py
```

Expected: all pass.

- [ ] **Step 2: Run frontend build**

Run:

```bash
npm run build
```

Expected: pass.

- [ ] **Step 3: Manual API smoke test**

Run:

```bash
./.venv/bin/python - <<'PY'
from backend.repository import LedgerRepository
from pathlib import Path
from tempfile import TemporaryDirectory

with TemporaryDirectory() as d:
    repo = LedgerRepository(Path(d) / "ledger.db", sandbox_root=Path(d) / "sandboxes")
    repo.initialize()
    easy = repo.create_check("tenant-cache-isolation", difficulty="easy")
    medium = repo.create_check("tenant-cache-isolation", difficulty="medium")
    hard = repo.create_check("tenant-cache-isolation", difficulty="hard")
    print(easy["difficulty"], [step["type"] for step in easy["plan"]["steps"]])
    print(medium["difficulty"], [step["type"] for step in medium["plan"]["steps"]])
    print(hard["difficulty"], [step["type"] for step in hard["plan"]["steps"]])
PY
```

Expected output:

```text
easy ['multiple_choice', 'multiple_choice']
medium ['multiple_choice', 'sandbox']
hard ['sandbox']
```

- [ ] **Step 4: Commit final fixes if needed**

If any verification fix was needed:

```bash
git add <changed-files>
git commit -m "fix: stabilize difficulty plan flow"
```

- [ ] **Step 5: Push**

```bash
git push origin main
```

Expected: branch updates on GitHub.

---

## Self-Review

- Spec coverage: easy multiple-choice only is covered by `tenant-cache-easy`; medium mixed plan is covered by `tenant-cache-medium`; hard current workflow is covered by `tenant-cache-hard`; backend ownership is covered by `plan_json`; server-side validation is covered by `submit_check_answers`.
- Placeholder scan: no implementation step relies on unnamed functions or unspecified files. The only JSX move in Task 6 says to move existing editor JSX because duplicating the whole existing editor block in a plan would create drift; the exact gating conditions and surrounding code are specified.
- Type consistency: `difficulty`, `template_id`, `plan`, `steps`, `questions`, `answers`, and `results` are named consistently across backend and frontend tasks.
