from backend.db import connect, initialize_schema
from backend.repository import LedgerRepository
from backend.ingestion import ClaudeCodeAdapter, CodexAdapter


def test_repository_seeds_demo_project_and_topics(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.initialize()

    projects = repo.list_projects()
    assert [project["slug"] for project in projects] == ["docs-search-api"]

    topics = repo.list_topics("docs-search-api")
    assert len(topics) == 4
    assert topics[0]["state"] == "check_recommended"
    assert "tenant" in topics[0]["title"].lower()


def test_seeded_topic_has_revision(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.initialize()

    topic = repo.get_topic("tenant-cache-isolation")

    assert topic["current_revision"]["id"] == "tenant-cache-isolation-rev-1"
    assert topic["current_revision"]["topic_id"] == "tenant-cache-isolation"
    assert topic["current_revision"]["revision"] == 1
    assert topic["current_revision"]["commit_sha"] == "demo-seed"
    assert topic["current_revision"]["code_path"] == "retrieval/rerank.py"


def test_seeded_topic_has_session_grounded_claude_receipt(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.initialize()

    topic = repo.get_topic("tenant-cache-isolation")
    receipt = next(item for item in topic["evidence"] if item["kind"] == "claude_receipt")

    assert receipt["provider"] == "claude_code"
    assert receipt["session_id"] == "claude-demo-session"
    assert receipt["source_path"] == "~/.claude/projects/demo.jsonl"
    assert receipt["tool_sequence"] == [
        "Read retrieval/rerank.py",
        "Edit retrieval/rerank.py",
        "Bash python -m pytest",
    ]
    assert receipt["link_confidence"] == "hand_verified"


def test_initialize_backfills_missing_seeded_revision(tmp_path):
    db_path = tmp_path / "ledger.db"
    with connect(db_path) as conn:
        initialize_schema(conn)
        conn.execute(
            "INSERT INTO projects (id, slug, name, repo_path) VALUES (?, ?, ?, ?)",
            ("project-docs-search-api", "docs-search-api", "Docs Search API", "/demo/docs-search-api"),
        )
        conn.execute(
            """
            INSERT INTO topics
            (id, project_id, provider, title, state, summary, why_now, risk_class, caller_count, claude_authored, rank)
            VALUES (?, 'project-docs-search-api', 'claude_code', ?, 'check_recommended', ?, ?, 'persistence', 5, 1, 1)
            """,
            (
                "tenant-cache-isolation",
                "Tenant isolation in retrieval cache",
                "Cached retrieval results must never cross tenant boundaries.",
                "Claude touched the retrieval path.",
            ),
        )
        conn.commit()

    repo = LedgerRepository(db_path)
    repo.initialize()

    topic = repo.get_topic("tenant-cache-isolation")
    assert topic["current_revision"]["id"] == "tenant-cache-isolation-rev-1"


def test_initialize_backfills_seeded_receipt_grounding(tmp_path):
    db_path = tmp_path / "ledger.db"
    with connect(db_path) as conn:
        initialize_schema(conn)
        conn.execute(
            "INSERT INTO projects (id, slug, name, repo_path) VALUES (?, ?, ?, ?)",
            ("project-docs-search-api", "docs-search-api", "Docs Search API", "/demo/docs-search-api"),
        )
        conn.execute(
            """
            INSERT INTO topics
            (id, project_id, provider, title, state, summary, why_now, risk_class, caller_count, claude_authored, rank)
            VALUES (?, 'project-docs-search-api', 'claude_code', ?, 'check_recommended', ?, ?, 'persistence', 5, 1, 1)
            """,
            (
                "tenant-cache-isolation",
                "Tenant isolation in retrieval cache",
                "Cached retrieval results must never cross tenant boundaries.",
                "Claude touched the retrieval path.",
            ),
        )
        conn.execute(
            "INSERT INTO evidence (topic_id, provider, kind, title, body) VALUES (?, ?, ?, ?, ?)",
            (
                "tenant-cache-isolation",
                "claude_code",
                "claude_receipt",
                "Claude Code session",
                "Read retrieval/rerank.py -> Edit retrieval/rerank.py -> Bash python -m pytest.",
            ),
        )
        conn.commit()

    repo = LedgerRepository(db_path)
    repo.initialize()

    topic = repo.get_topic("tenant-cache-isolation")
    receipt = next(item for item in topic["evidence"] if item["kind"] == "claude_receipt")
    assert receipt["session_id"] == "claude-demo-session"
    assert receipt["link_confidence"] == "hand_verified"


def test_check_lifecycle_persists_attempt_and_completion(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    check = repo.create_check("tenant-cache-isolation")
    assert check["state"] == "in_progress"
    assert check["sandbox_path"]
    assert check["topic_revision_id"] == "tenant-cache-isolation-rev-1"

    result = repo.run_check(check["id"])
    assert result["passed"] is False
    assert "test_filters_documents_by_tenant" in result["output"]

    file_state = repo.read_check_file(check["id"], "retrieval/rerank.py")
    assert "return list(documents)" in file_state["content"]

    fixed = file_state["content"].replace("return list(documents)", "return [doc for doc in documents if doc.tenant_id == tenant_id]")
    repo.update_check_file(check["id"], "retrieval/rerank.py", fixed)

    result = repo.run_check(check["id"])
    assert result["passed"] is True

    completed = repo.complete_check(check["id"])
    assert completed["state"] == "completed"
    assert completed["run_count"] == 2

    events = repo.list_topic_events("tenant-cache-isolation")
    assert events[-1]["event_type"] == "practiced"
    assert events[-1]["topic_revision_id"] == "tenant-cache-isolation-rev-1"


def test_hook_event_initializes_project_and_topics_from_repo(tmp_path):
    repo_path = tmp_path / "docs-api"
    retrieval_dir = repo_path / "retrieval"
    retrieval_dir.mkdir(parents=True)
    (retrieval_dir / "rerank.py").write_text(
        "def visible_documents_for_tenant(documents, tenant_id):\n"
        "    return [doc for doc in documents if doc.tenant_id == tenant_id]\n"
    )

    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    result = repo.record_hook_event(
        event_type="post-commit",
        cwd=str(repo_path),
        branch="main",
        head_sha="abc123",
        payload={"changed_files": ["retrieval/rerank.py"]},
    )

    project = result["project"]
    assert project["slug"] == "docs-api"
    assert project["repo_path"] == str(repo_path)

    topics = repo.list_topics("docs-api")
    assert topics
    hook_topic = next(topic for topic in topics if "retrieval/rerank.py" in topic["summary"])

    topic = repo.get_topic(hook_topic["id"])
    evidence = {(item["kind"], item["title"]) for item in topic["evidence"]}
    assert ("code", "retrieval/rerank.py") in evidence
    assert ("hook_event", "post-commit on main") in evidence
    assert topic["current_revision"]["code_path"] == "retrieval/rerank.py"

    check = repo.create_check(hook_topic["id"])
    assert check["topic_revision_id"] == topic["current_revision"]["id"]


def test_claude_code_hook_event_labels_provider_on_event_and_evidence(tmp_path):
    repo_path = tmp_path / "docs-api"
    retrieval_dir = repo_path / "retrieval"
    retrieval_dir.mkdir(parents=True)
    (retrieval_dir / "rerank.py").write_text("def rerank():\n    return []\n")

    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    result = repo.record_hook_event(
        event_type="SessionStart",
        cwd=str(repo_path),
        branch="main",
        head_sha="abc123",
        payload={"changed_files": ["retrieval/rerank.py"]},
    )

    assert result["event"]["provider"] == "claude_code"
    assert result["topics"][0]["provider"] == "claude_code"
    hook_topic = next(topic for topic in result["topics"] if "retrieval/rerank.py" in topic["summary"])
    topic = repo.get_topic(hook_topic["id"])
    assert {item["provider"] for item in topic["evidence"]} == {"claude_code"}


def test_hook_event_records_session_grounded_receipt_evidence(tmp_path):
    repo_path = tmp_path / "docs-api"
    retrieval_dir = repo_path / "retrieval"
    retrieval_dir.mkdir(parents=True)
    (retrieval_dir / "rerank.py").write_text("def rerank():\n    return []\n")

    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    result = repo.record_hook_event(
        provider="codex",
        event_type="SessionStart",
        cwd=str(repo_path),
        branch="main",
        head_sha="abc123",
        payload={
            "changed_files": ["retrieval/rerank.py"],
            "session_id": "codex-session-1",
            "source_path": "~/.codex/sessions/session-1.jsonl",
            "tool_sequence": ["Read retrieval/rerank.py", "Edit retrieval/rerank.py"],
            "link_confidence": "hand_verified",
        },
    )

    hook_topic = next(item for item in result["topics"] if "retrieval/rerank.py" in item["summary"])
    topic = repo.get_topic(hook_topic["id"])
    receipt = next(item for item in topic["evidence"] if item["kind"] == "codex_receipt")

    assert result["event"]["provider"] == "codex"
    assert receipt["provider"] == "codex"
    assert receipt["session_id"] == "codex-session-1"
    assert receipt["source_path"] == "~/.codex/sessions/session-1.jsonl"
    assert receipt["tool_sequence"] == ["Read retrieval/rerank.py", "Edit retrieval/rerank.py"]
    assert receipt["link_confidence"] == "hand_verified"
    assert repo.get_session("codex-session-1")["provider"] == "codex"


def test_codex_adapter_normalizes_to_provider_labeled_event(tmp_path):
    repo_path = tmp_path / "docs-api"
    repo_path.mkdir()

    event = CodexAdapter().normalize(
        {
            "event_type": "SessionStart",
            "cwd": str(repo_path),
            "branch": "main",
            "head_sha": "abc123",
            "changed_files": ["retrieval/rerank.py"],
        }
    )

    assert event.provider == "codex"
    assert event.cwd == str(repo_path)
    assert event.payload["changed_files"] == ["retrieval/rerank.py"]


def test_codex_adapter_preserves_receipt_grounding_fields(tmp_path):
    repo_path = tmp_path / "docs-api"
    repo_path.mkdir()

    event = CodexAdapter().normalize(
        {
            "event_type": "SessionStart",
            "cwd": str(repo_path),
            "branch": "main",
            "head_sha": "abc123",
            "changed_files": ["retrieval/rerank.py"],
            "session_id": "codex-session-1",
            "source_path": "~/.codex/sessions/session-1.jsonl",
            "tool_sequence": ["Read retrieval/rerank.py", "Edit retrieval/rerank.py"],
            "link_confidence": "hand_verified",
        }
    )

    assert event.payload["session_id"] == "codex-session-1"
    assert event.payload["source_path"] == "~/.codex/sessions/session-1.jsonl"
    assert event.payload["tool_sequence"] == ["Read retrieval/rerank.py", "Edit retrieval/rerank.py"]
    assert event.payload["link_confidence"] == "hand_verified"


def test_claude_code_adapter_is_default_priority_provider(tmp_path):
    repo_path = tmp_path / "docs-api"
    repo_path.mkdir()

    event = ClaudeCodeAdapter().normalize(
        {
            "event_type": "SessionStart",
            "cwd": str(repo_path),
            "branch": "main",
            "head_sha": "abc123",
            "changed_files": ["retrieval/rerank.py"],
        }
    )

    assert event.provider == "claude_code"
