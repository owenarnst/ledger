import shutil

from fastapi.testclient import TestClient

from backend.api import create_app


def test_api_exposes_project_topic_and_check_flow(tmp_path):
    app = create_app(db_path=tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    client = TestClient(app)

    projects = client.get("/api/projects")
    assert projects.status_code == 200
    assert projects.json()[0]["slug"] == "docs-search-api"

    topics = client.get("/api/projects/docs-search-api/topics")
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


def test_api_records_hook_event_without_minting_topics(tmp_path):
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
    # Ingestion records provenance only; it never mints a Topic (ADR-0002).
    assert body["topics"] == []
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
    assert body["topics"] == []


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


def test_api_extracts_a_real_repo_and_exposes_analysis(git_repo, tmp_path):
    repo_path, _sha = git_repo
    # Copy under a uniquely-named directory so the project slug never collides
    # with the curated demo project the API seeds on startup.
    target = tmp_path / "extract-target"
    shutil.copytree(repo_path, target)

    app = create_app(db_path=tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    client = TestClient(app)

    extracted = client.post("/api/extract", json={"repo_path": str(target)})
    assert extracted.status_code == 200
    body = extracted.json()
    assert body["surfaced"] >= 1
    assert body["analysis_source"] == "deterministic"
    assert body["topics"][0]["risk_class"] == "persistence"
    assert "tenant" in body["topics"][0]["title"].lower()

    # The discovery run is auditable and honestly sourced.
    slug = body["project"]["slug"]
    status = client.get(f"/api/projects/{slug}/analysis")
    assert status.status_code == 200
    assert status.json()["status"] == "verified"
    assert status.json()["analysis_source"] == "deterministic"
    assert status.json()["verified_count"] == body["surfaced"]


def test_api_analysis_endpoint_404s_for_unknown_project(tmp_path):
    app = create_app(db_path=tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    client = TestClient(app)

    response = client.get("/api/projects/nonexistent/analysis")

    assert response.status_code == 404
