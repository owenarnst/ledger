import json
from pathlib import Path

from backend import exercise_generation
from backend.__main__ import main
from backend.api import create_app
from backend.db import connect
from backend.hooks import HookSpool, build_session_start_nudge, reset_ledger
from backend.ingestion import ClaudeCodeAdapter, CodexAdapter
from backend.repository import LedgerRepository


def _clear_cached_exercise_plans(repo: LedgerRepository) -> None:
    """Drop the demo-seeded exercise-plan cache so a test exercises the generation
    path. The seed pre-caches the hero check's easy/medium plans (so the demo loads
    instantly); these tests instead verify what happens on a cache miss."""
    with connect(repo.db_path) as conn:
        conn.execute("DELETE FROM exercise_plans")
        conn.commit()


class FakeExerciseGenerator:
    provider = "fake-llm"

    def __init__(self):
        self.calls = 0

    def generate_plan(self, *, topic, revision, difficulty):
        self.calls += 1
        if difficulty == "hard":
            return {
                "template_id": "generated-hard",
                "difficulty": "hard",
                "steps": [{"type": "sandbox"}],
                "questions": [],
            }
        if difficulty == "medium":
            return {
                "template_id": "generated-medium",
                "difficulty": "medium",
                "steps": [
                    {"type": "multiple_choice", "question_id": "tenant-filter-purpose"},
                    {"type": "multiple_choice", "question_id": "tenant-filter-implementation"},
                    {"type": "sandbox"},
                ],
                "questions": [
                    {
                        "id": "tenant-filter-purpose",
                        "kind": "concept",
                        "prompt": "What property should the fix preserve?",
                        "choices": ["Tenant isolation", "Score sorting", "Object identity"],
                        "correct_index": 0,
                        "rationale": "The invariant is tenant isolation.",
                    },
                    {
                        "id": "tenant-filter-implementation",
                        "kind": "debugging",
                        "prompt": "Which implementation direction would fix the sandbox task?",
                        "choices": [
                            "def visible_documents_for_tenant(documents: list[Document], tenant_id: str) -> list[Document]:\n    return [doc for doc in documents if doc.tenant_id == tenant_id]",
                            "def visible_documents_for_tenant(documents: list[Document], tenant_id: str) -> list[Document]:\n    return list(documents)",
                            "def visible_documents_for_tenant(documents: list[Document], tenant_id: str) -> list[Document]:\n    return sorted(documents, key=lambda doc: doc.score, reverse=True)",
                        ],
                        "correct_index": 0,
                        "rationale": "This points at the tenant filter the learner still needs to implement in the sandbox.",
                    },
                ],
            }
        return {
            "template_id": "generated-easy",
            "difficulty": "easy",
            "steps": [
                {"type": "multiple_choice", "question_id": "tenant-filter-purpose"},
                {"type": "multiple_choice", "question_id": "tenant-filter-debug"},
            ],
            "questions": [
                {
                    "id": "tenant-filter-purpose",
                    "kind": "concept",
                    "prompt": "What should this function guarantee before returning documents?",
                    "choices": ["Only requested-tenant documents are returned", "All documents are returned", "Documents are grouped by score"],
                    "correct_index": 0,
                    "rationale": "The invariant is tenant isolation.",
                },
                {
                    "id": "tenant-filter-debug",
                    "kind": "debugging",
                    "prompt": "Which complete implementation fixes the behavior?",
                    "choices": [
                        "def visible_documents_for_tenant(documents: list[Document], tenant_id: str) -> list[Document]:\n    return [doc for doc in documents if doc.tenant_id == tenant_id]",
                        "def visible_documents_for_tenant(documents: list[Document], tenant_id: str) -> list[Document]:\n    return list(documents)",
                        "def visible_documents_for_tenant(documents: list[Document], tenant_id: str) -> list[Document]:\n    return sorted(documents, key=lambda doc: doc.score, reverse=True)",
                    ],
                    "correct_index": 0,
                    "rationale": "The failing test proves the tenant isolation invariant.",
                },
            ],
        }


def test_complete_check_persists_reflection_history(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()
    check = repo.create_check("tenant-cache-isolation")
    file_state = repo.read_check_file(check["id"], "retrieval/rerank.py")
    repo.update_check_file(
        check["id"],
        "retrieval/rerank.py",
        file_state["content"].replace(
            "return list(documents)",
            "return [doc for doc in documents if doc.tenant_id == tenant_id]",
        ),
    )
    repo.run_check(check["id"])

    completed = repo.complete_check(
        check["id"],
        reflection={
            "invariant": "Only documents for the requested tenant may be ranked.",
            "rationale": "The retrieval cache can otherwise leak cross-tenant data.",
            "future_risk": "A cache-key refactor could omit tenant_id.",
        },
    )

    assert completed["state"] == "completed"
    reflections = repo.list_reflections("tenant-cache-isolation")
    assert reflections[0]["invariant"].startswith("Only documents")
    assert reflections[0]["check_id"] == check["id"]


def test_run_check_records_graceful_failure_when_runner_errors(tmp_path, monkeypatch):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()
    check = repo.create_check("tenant-cache-isolation")

    def broken_runner(_sandbox_path):
        raise RuntimeError("pytest executable disappeared")

    monkeypatch.setattr("backend.repository.run_pytest", broken_runner)

    result = repo.run_check(check["id"])

    assert result["passed"] is False
    assert "pytest executable disappeared" in result["output"]
    assert repo.get_check(check["id"])["run_count"] == 1


def test_pseudocode_comments_preserve_code_and_mark_suspicious_line(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()
    check = repo.create_check("tenant-cache-isolation")
    original = repo.read_check_file(check["id"], "retrieval/rerank.py")["content"]

    result = repo.pseudocode_comments(check["id"], "retrieval/rerank.py")

    assert result["changed"] is True
    assert "return list(documents)" in result["content"]
    assert "Plan: accept the input collection and the requested tenant." in result["content"]
    assert "requested tenant" in result["content"]
    assert result["content"].count("return list(documents)") == original.count("return list(documents)")
    assert "LEDGER" not in result["content"]
    assert "Check this line:" not in result["content"]


def test_pseudocode_comments_are_idempotent(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()
    check = repo.create_check("tenant-cache-isolation")

    first = repo.pseudocode_comments(check["id"], "retrieval/rerank.py")["content"]
    second = repo.pseudocode_comments(check["id"], "retrieval/rerank.py")["content"]

    assert second == first


def test_pseudocode_comments_remove_legacy_check_line_comments(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()
    check = repo.create_check("tenant-cache-isolation")
    file_state = repo.read_check_file(check["id"], "retrieval/rerank.py")
    with_legacy = file_state["content"].replace(
        "    return list(documents)",
        "    # Check this line: compare this with the invariant: Candidate documents must be filtered by tenant_id before ranking.\n    return list(documents)",
    )
    repo.update_check_file(check["id"], "retrieval/rerank.py", with_legacy)

    result = repo.pseudocode_comments(check["id"], "retrieval/rerank.py")

    assert "Check this line:" not in result["content"]
    assert "return list(documents)" in result["content"]


def test_easy_check_returns_multiple_choice_only_plan(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes", exercise_generator=FakeExerciseGenerator())
    repo.initialize()
    _clear_cached_exercise_plans(repo)

    check = repo.create_check("tenant-cache-isolation", difficulty="easy")

    assert check["difficulty"] == "easy"
    assert check["template_id"] == "generated-easy"
    assert [step["type"] for step in check["plan"]["steps"]] == ["multiple_choice", "multiple_choice"]
    assert "correct_index" not in str(check["plan"])
    assert check["plan"]["questions"][0]["kind"] == "concept"
    assert check["plan"]["questions"][1]["kind"] == "debugging"
    assert check["plan"]["questions"][1]["choices"][0].startswith("def visible_documents_for_tenant")
    assert "\n    return " in check["plan"]["questions"][1]["choices"][0]


def test_easy_fallback_plan_is_multiple_choice_only():
    plan = exercise_generation.fallback_plan("easy")

    assert plan["difficulty"] == "easy"
    assert all(step["type"] == "multiple_choice" for step in plan["steps"])
    assert plan["questions"]


def test_medium_check_uses_generated_implementation_hint_then_sandbox_plan(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes", exercise_generator=FakeExerciseGenerator())
    repo.initialize()
    _clear_cached_exercise_plans(repo)

    check = repo.create_check("tenant-cache-isolation", difficulty="medium")

    assert check["difficulty"] == "medium"
    assert check["template_id"] == "generated-medium"
    assert [step["type"] for step in check["plan"]["steps"]] == ["multiple_choice", "multiple_choice", "sandbox"]
    assert check["plan"]["steps"][0]["question_id"] == "tenant-filter-purpose"
    assert check["plan"]["steps"][1]["question_id"] == "tenant-filter-implementation"
    assert check["plan"]["questions"][0]["kind"] == "concept"
    assert check["plan"]["questions"][1]["kind"] == "debugging"
    assert check["plan"]["questions"][1]["choices"][0].startswith("def visible_documents_for_tenant")


def test_cli_exercise_generator_falls_back_from_claude_to_codex(monkeypatch):
    calls = []

    def fake_run_generator_cli(provider, prompt, timeout_seconds):
        calls.append(provider)
        if provider == "claude":
            return ""
        return json.dumps(
            {
                "template_id": "generated-medium",
                "difficulty": "medium",
                "steps": [
                    {"type": "multiple_choice", "question_id": "tenant-filter-purpose"},
                    {"type": "sandbox"},
                ],
                "questions": [
                    {
                        "id": "tenant-filter-purpose",
                        "kind": "concept",
                        "prompt": "What invariant matters?",
                        "choices": ["Tenant isolation", "Score ordering", "Text length"],
                        "correct_index": 0,
                        "rationale": "The sandbox fix must preserve tenant isolation.",
                    }
                ],
            }
        )

    monkeypatch.setattr(exercise_generation, "run_generator_cli", fake_run_generator_cli)
    generator = exercise_generation.CliExercisePlanGenerator(provider="claude", fallback_provider="codex")

    plan = generator.generate_plan(
        topic={"title": "Tenant visibility", "summary": "Filter tenant documents."},
        revision={"invariant": "Candidate documents must be filtered by tenant_id.", "code_path": "backend/search.py"},
        difficulty="medium",
    )

    assert calls == ["claude", "codex"]
    assert plan["template_id"] == "generated-medium"
    assert [step["type"] for step in plan["steps"]] == ["multiple_choice", "sandbox"]


def test_generated_exercise_plan_is_stored_and_reused(tmp_path):
    generator = FakeExerciseGenerator()
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes", exercise_generator=generator)
    repo.initialize()
    _clear_cached_exercise_plans(repo)

    first = repo.create_check("tenant-cache-isolation", difficulty="medium")
    second = repo.create_check("tenant-cache-isolation", difficulty="medium")

    assert generator.calls == 1
    assert first["plan"] == second["plan"]


def test_hard_check_keeps_current_sandbox_plan(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    check = repo.create_check("tenant-cache-isolation", difficulty="hard")

    assert check["difficulty"] == "hard"
    assert check["template_id"] == "generated-hard-fallback"
    assert [step["type"] for step in check["plan"]["steps"]] == ["sandbox"]
    assert check["target_file"] == "retrieval/rerank.py"


def test_each_topic_stages_its_own_sandbox_exercise(tmp_path):
    """Every seeded topic's check stages an exercise in its own target file, and
    the injected bug breaks the hero suite while restoring the documented fix makes
    it pass. Guards against the regression where every topic silently handed the
    learner the tenant-isolation exercise."""
    from backend.sandbox import SANDBOX_SPECS, run_pytest

    repo = LedgerRepository(
        tmp_path / "ledger.db",
        sandbox_root=tmp_path / "sandboxes",
        exercise_generator=FakeExerciseGenerator(),
    )
    repo.initialize()

    expected_targets = {
        "tenant-cache-isolation": "retrieval/rerank.py",
        "docs-search-api-rerank-rerank": "retrieval/rerank.py",
        "docs-search-api-context-context": "retrieval/context.py",
    }
    for topic_id, target in expected_targets.items():
        check = repo.create_check(topic_id, difficulty="hard")
        assert check["target_file"] == target, topic_id

        sandbox = Path(check["sandbox_path"])
        assert not run_pytest(sandbox).passed, f"{topic_id}: injected bug did not fail any test"

        spec = SANDBOX_SPECS[topic_id]
        edited = sandbox / spec.target_file
        edited.write_text(edited.read_text().replace(spec.mutated, spec.original))
        assert run_pytest(sandbox).passed, f"{topic_id}: documented fix did not pass the suite"


def test_demo_seed_precaches_exercise_plans_for_every_topic(tmp_path):
    """The demo seed pre-caches every topic's easy/medium plans so the Debug-to-Own
    MCQs load instantly and deterministically — no live ``claude -p`` round-trip on
    first open. easy is multiple-choice only; medium ends in the topic's sandbox.
    Regression guard for the demo experience across all seeded topics."""

    class ExplodingGenerator:
        provider = "should-not-run"

        def generate_plan(self, *, topic, revision, difficulty):
            raise AssertionError(f"live generation ran for {difficulty}; expected a cache hit")

    repo = LedgerRepository(
        tmp_path / "ledger.db",
        sandbox_root=tmp_path / "sandboxes",
        exercise_generator=ExplodingGenerator(),
    )
    repo.initialize()

    topic_ids = [
        "tenant-cache-isolation",
        "docs-search-api-rerank-rerank",
        "docs-search-api-context-context",
    ]
    for topic_id in topic_ids:
        # both are served straight from the seeded cache: the generator, which
        # raises if called, never runs.
        easy = repo.create_check(topic_id, difficulty="easy")
        medium = repo.create_check(topic_id, difficulty="medium")

        easy_steps = [step["type"] for step in easy["plan"]["steps"]]
        assert easy["difficulty"] == "easy"
        assert easy_steps and all(kind == "multiple_choice" for kind in easy_steps), topic_id

        medium_steps = [step["type"] for step in medium["plan"]["steps"]]
        assert medium["difficulty"] == "medium"
        assert "multiple_choice" in medium_steps, topic_id
        assert medium_steps[-1] == "sandbox", topic_id

        # served plans never leak the answer key
        assert "correct_index" not in str(easy["plan"]), topic_id
        assert "correct_index" not in str(medium["plan"]), topic_id


def test_submit_check_answers_validates_easy_mode_server_side(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes", exercise_generator=FakeExerciseGenerator())
    repo.initialize()
    _clear_cached_exercise_plans(repo)
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
    assert repo.get_check(check["id"])["state"] == "completed"


def test_submit_check_answers_records_wrong_answer(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes", exercise_generator=FakeExerciseGenerator())
    repo.initialize()
    _clear_cached_exercise_plans(repo)
    check = repo.create_check("tenant-cache-isolation", difficulty="easy")

    result = repo.submit_check_answers(check["id"], {"tenant-filter-purpose": 1, "tenant-filter-debug": 0})

    assert result["passed"] is False
    assert result["results"][0]["correct"] is False
    assert result["results"][0]["selected_index"] == 1
    assert repo.get_check(check["id"])["state"] == "in_progress"


def test_contract_alias_routes_are_registered(tmp_path):
    app = create_app(db_path=tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    paths = {route.path for route in app.routes}

    assert "/api/topics" in paths
    assert "/api/checks" in paths
    assert "/api/coach" in paths
    assert "/api/reset" in paths
    assert "/api/checks/{check_id}/pseudocode-comments" in paths
    assert "/api/checks/{check_id}/answers" in paths
    assert "/api/topics/{topic_id}/reflections" in paths
    # Agentic discovery routes (ADR-0002).
    assert "/api/extract" in paths
    assert "/api/projects/{project_slug}/analysis" in paths


def test_claude_adapter_reads_jsonl_session_records(tmp_path):
    log_path = tmp_path / "session.jsonl"
    log_path.write_text(
        "\n".join(
            [
                json.dumps({"sessionId": "claude-session-1", "cwd": str(tmp_path / "repo")}),
                json.dumps(
                    {
                        "sessionId": "claude-session-1",
                        "cwd": str(tmp_path / "repo"),
                        "message": {
                            "content": [
                                {"type": "tool_use", "name": "Read", "input": {"file_path": "retrieval/rerank.py"}},
                                {"type": "tool_use", "name": "Edit", "input": {"file_path": "retrieval/rerank.py"}},
                            ]
                        },
                    }
                ),
            ]
        )
        + "\n"
    )

    events = ClaudeCodeAdapter().read_sessions(tmp_path)

    assert len(events) == 1
    assert events[0].provider == "claude_code"
    assert events[0].payload["session_id"] == "claude-session-1"
    assert events[0].payload["changed_files"] == ["retrieval/rerank.py"]
    assert events[0].payload["tool_sequence"] == ["Read retrieval/rerank.py", "Edit retrieval/rerank.py"]
    assert events[0].payload["source_path"].endswith("session.jsonl:2")


def test_codex_adapter_reads_jsonl_session_records(tmp_path):
    log_path = tmp_path / "codex.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "session_id": "codex-session-1",
                "cwd": str(tmp_path / "repo"),
                "tool_calls": [
                    {"name": "Read", "path": "retrieval/rerank.py"},
                    {"name": "Edit", "path": "retrieval/rerank.py"},
                ],
            }
        )
        + "\n"
    )

    events = CodexAdapter().read_sessions(tmp_path)

    assert len(events) == 1
    assert events[0].provider == "codex"
    assert events[0].payload["session_id"] == "codex-session-1"
    assert events[0].payload["changed_files"] == ["retrieval/rerank.py"]


def test_import_provider_sessions_records_session_provenance(tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / "retrieval").mkdir(parents=True)
    (repo_path / "retrieval" / "rerank.py").write_text("def rerank():\n    return []\n")
    log_path = tmp_path / "logs" / "codex.jsonl"
    log_path.parent.mkdir()
    log_path.write_text(
        json.dumps(
            {
                "session_id": "codex-session-1",
                "cwd": str(repo_path),
                "tool_calls": [{"name": "Edit", "path": "retrieval/rerank.py"}],
            }
        )
        + "\n"
    )
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.initialize()

    result = repo.import_provider_sessions("codex", log_path.parent)

    # Importing sessions records provenance only; it never mints a Topic.
    assert result["imported"] == 1
    assert result["topics"] == []
    assert repo.get_session("codex-session-1")["provider"] == "codex"


def test_hook_spool_drains_fifo_json_events(tmp_path):
    spool = HookSpool(tmp_path / "spool")
    spool.write({"event_type": "post-commit", "cwd": "/repo", "head_sha": "a"})
    spool.write({"event_type": "SessionStart", "cwd": "/repo", "head_sha": "b"})

    events = spool.drain()

    assert [event["head_sha"] for event in events] == ["a", "b"]
    assert spool.pending_count() == 0


def test_session_start_nudge_reports_ready_checks(tmp_path):
    repo_path = tmp_path / "docs-search-api"
    repo_path.mkdir()
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.initialize()

    line = build_session_start_nudge(repo, cwd=repo_path, base_url="http://127.0.0.1:4317")

    assert line == (
        "Ledger: 3 checks ready for docs-search-api. "
        "If Claude just helped with a complex change, this is a good moment to test your understanding. "
        "Open http://127.0.0.1:4317/p/docs-search-api"
    )


def test_reset_ledger_recreates_database_and_clears_spool(tmp_path):
    db_path = tmp_path / "ledger.db"
    spool = HookSpool(tmp_path / "spool")
    spool.write({"event_type": "post-commit", "cwd": "/repo"})
    repo = LedgerRepository(db_path)
    repo.initialize()

    reset_ledger(db_path=db_path, sandbox_root=tmp_path / "sandboxes", spool_dir=tmp_path / "spool")

    fresh = LedgerRepository(db_path)
    fresh.initialize()
    assert fresh.list_projects()[0]["slug"] == "docs-search-api"
    assert spool.pending_count() == 0


def test_cli_reset_and_nudge_commands(tmp_path, capsys):
    db_path = tmp_path / "ledger.db"
    sandbox_root = tmp_path / "sandboxes"
    repo_path = tmp_path / "docs-search-api"
    repo_path.mkdir()

    assert main(["reset", "--db", str(db_path), "--sandbox-root", str(sandbox_root)]) == 0
    assert main(["nudge", "--db", str(db_path), "--cwd", str(repo_path), "--base-url", "http://ledger.local"]) == 0

    output = capsys.readouterr().out
    assert "Reset Ledger at" in output
    assert "Ledger: 3 checks ready for docs-search-api" in output
