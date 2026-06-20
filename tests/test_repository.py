from ledger_backend.repository import LedgerRepository
from ledger_backend.ingestion import ClaudeCodeAdapter, CodexAdapter


def test_repository_seeds_demo_project_and_topics(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.initialize()

    projects = repo.list_projects()
    assert [project["slug"] for project in projects] == ["docs-api"]

    topics = repo.list_topics("docs-api")
    assert len(topics) == 4
    assert topics[0]["state"] == "check_recommended"
    assert "tenant" in topics[0]["title"].lower()


def test_check_lifecycle_persists_attempt_and_completion(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    check = repo.create_check("tenant-cache-isolation")
    assert check["state"] == "in_progress"
    assert check["sandbox_path"]

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
    topic = repo.get_topic(result["topics"][0]["id"])
    assert {item["provider"] for item in topic["evidence"]} == {"claude_code"}


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
