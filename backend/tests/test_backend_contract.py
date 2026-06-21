import json

from backend.__main__ import main
from backend.api import create_app
from backend.hooks import HookSpool, build_session_start_nudge, reset_ledger
from backend.ingestion import ClaudeCodeAdapter, CodexAdapter
from backend.repository import LedgerRepository


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
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    check = repo.create_check("tenant-cache-isolation", difficulty="easy")

    assert check["difficulty"] == "easy"
    assert check["template_id"] == "tenant-cache-easy"
    assert [step["type"] for step in check["plan"]["steps"]] == ["multiple_choice", "multiple_choice"]
    assert "correct_index" not in str(check["plan"])
    assert check["plan"]["questions"][0]["kind"] == "concept"
    assert check["plan"]["questions"][1]["kind"] == "debugging"
    assert check["plan"]["questions"][1]["choices"][0].startswith("def visible_documents_for_tenant")
    assert "\n    return " in check["plan"]["questions"][1]["choices"][0]


def test_medium_check_returns_two_questions_then_sandbox_plan(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    check = repo.create_check("tenant-cache-isolation", difficulty="medium")

    assert check["difficulty"] == "medium"
    assert check["template_id"] == "tenant-cache-medium"
    assert [step["type"] for step in check["plan"]["steps"]] == ["multiple_choice", "multiple_choice", "sandbox"]
    assert check["plan"]["steps"][0]["question_id"] == "tenant-filter-purpose"
    assert check["plan"]["steps"][1]["question_id"] == "tenant-filter-debug"
    assert check["plan"]["questions"][0]["kind"] == "concept"
    assert check["plan"]["questions"][1]["kind"] == "debugging"


def test_hard_check_keeps_current_sandbox_plan(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    check = repo.create_check("tenant-cache-isolation", difficulty="hard")

    assert check["difficulty"] == "hard"
    assert check["template_id"] == "tenant-cache-hard"
    assert [step["type"] for step in check["plan"]["steps"]] == ["sandbox"]
    assert check["target_file"] == "retrieval/rerank.py"


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
    assert repo.get_check(check["id"])["state"] == "completed"


def test_submit_check_answers_records_wrong_answer(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()
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


def test_import_provider_sessions_creates_provider_receipt(tmp_path):
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

    assert result["imported"] == 1
    topic = repo.get_topic(next(item["id"] for item in result["topics"] if "retrieval/rerank.py" in item["summary"]))
    assert any(item["kind"] == "codex_receipt" for item in topic["evidence"])


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

    assert line == "Ledger: 3 checks ready for docs-search-api · Open http://127.0.0.1:4317/p/docs-search-api"


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
