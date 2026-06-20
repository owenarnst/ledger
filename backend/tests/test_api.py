from fastapi.testclient import TestClient

from backend.api import create_app


def test_api_exposes_project_topic_and_check_flow(tmp_path):
    app = create_app(db_path=tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    client = TestClient(app)

    projects = client.get("/api/projects")
    assert projects.status_code == 200
    assert projects.json()[0]["slug"] == "docs-api"

    topics = client.get("/api/projects/docs-api/topics")
    assert topics.status_code == 200
    topic_id = topics.json()[0]["id"]

    topic = client.get(f"/api/topics/{topic_id}")
    assert topic.status_code == 200
    assert topic.json()["evidence"]

    check = client.post(f"/api/topics/{topic_id}/checks")
    assert check.status_code == 200
    check_id = check.json()["id"]

    run = client.post(f"/api/checks/{check_id}/run")
    assert run.status_code == 200
    assert run.json()["passed"] is False


def test_api_records_hook_event_and_refreshes_topics(tmp_path):
    repo_path = tmp_path / "docs-api"
    retrieval_dir = repo_path / "retrieval"
    retrieval_dir.mkdir(parents=True)
    (retrieval_dir / "rerank.py").write_text(
        "def visible_documents_for_tenant(documents, tenant_id):\n"
        "    return [doc for doc in documents if doc.tenant_id == tenant_id]\n"
    )
    app = create_app(db_path=tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    client = TestClient(app)

    response = client.post(
        "/api/hooks/events",
        json={
            "event_type": "SessionStart",
            "cwd": str(repo_path),
            "branch": "main",
            "head_sha": "abc123",
            "changed_files": ["retrieval/rerank.py"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["slug"] == "docs-api"
    assert body["topics"]
    assert body["event"]["event_type"] == "SessionStart"


def test_api_defaults_hook_provider_to_claude_code(tmp_path):
    repo_path = tmp_path / "docs-api"
    retrieval_dir = repo_path / "retrieval"
    retrieval_dir.mkdir(parents=True)
    (retrieval_dir / "rerank.py").write_text("def rerank():\n    return []\n")
    app = create_app(db_path=tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    client = TestClient(app)

    response = client.post(
        "/api/hooks/events",
        json={
            "event_type": "SessionStart",
            "cwd": str(repo_path),
            "branch": "main",
            "head_sha": "abc123",
            "changed_files": ["retrieval/rerank.py"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["event"]["provider"] == "claude_code"
    assert body["topics"][0]["provider"] == "claude_code"


def test_api_accepts_codex_provider_for_ingestion_only(tmp_path):
    repo_path = tmp_path / "docs-api"
    retrieval_dir = repo_path / "retrieval"
    retrieval_dir.mkdir(parents=True)
    (retrieval_dir / "rerank.py").write_text("def rerank():\n    return []\n")
    app = create_app(db_path=tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    client = TestClient(app)

    response = client.post(
        "/api/hooks/events",
        json={
            "provider": "codex",
            "event_type": "SessionStart",
            "cwd": str(repo_path),
            "branch": "main",
            "head_sha": "abc123",
            "changed_files": ["retrieval/rerank.py"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["event"]["provider"] == "codex"
