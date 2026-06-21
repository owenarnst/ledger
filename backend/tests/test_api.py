from fastapi.testclient import TestClient

from backend.api import create_app


def test_api_exposes_project_topic_and_check_flow(tmp_path):
    app = create_app(db_path=tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    client = TestClient(app)

    # A fresh install is honestly empty until the demo is explicitly seeded.
    assert client.get("/api/projects").json() == []
    seeded = client.post("/api/seed-demo")
    assert seeded.status_code == 200

    projects = client.get("/api/projects")
    assert projects.status_code == 200
    assert projects.json()[0]["slug"] == "docs-api"
    assert projects.json()[0]["is_demo"] == 1

    topics = client.get("/api/projects/docs-api/topics")
    assert topics.status_code == 200
    hero_row = topics.json()[0]  # rank 1 = the checkable hero topic
    topic_id = hero_row["id"]
    # Derived display facts ride the worklist rows (ADR-0002 / #22).
    assert hero_row["ownership_status"] == "Check recommended"
    assert hero_row["impact_level"] in ("high", "medium", "low")
    assert "code anchor" in hero_row["evidence_summary"]

    topic = client.get(f"/api/topics/{topic_id}")
    assert topic.status_code == 200
    detail = topic.json()
    assert detail["checkable"] == 1
    # Grouped, provider-neutral evidence; the retired trail section is gone.
    assert detail["code_anchors"]
    assert all(item["kind"] != "missing_reasoning" for item in detail["evidence"])
    assert detail["development_traces"]  # the hand-verified Claude receipt

    check = client.post(f"/api/topics/{topic_id}/checks")
    assert check.status_code == 200
    check_id = check.json()["id"]

    run = client.post(f"/api/checks/{check_id}/run")
    assert run.status_code == 200
    assert run.json()["passed"] is False


def test_api_refuses_check_for_non_checkable_topic(tmp_path):
    app = create_app(db_path=tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    client = TestClient(app)
    client.post("/api/seed-demo")

    response = client.post("/api/topics/rerank-threshold/checks")

    assert response.status_code == 409


def test_api_extracts_then_curates_a_real_repo(git_repo, tmp_path):
    repo_path, sha = git_repo
    app = create_app(db_path=tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    client = TestClient(app)

    extracted = client.post("/api/extract", json={"repo_path": str(repo_path)})
    assert extracted.status_code == 200
    body = extracted.json()
    assert body["surfaced"] >= 1
    assert body["analysis_source"] == "deterministic"
    assert all(topic["checkable"] == 0 for topic in body["topics"])

    # The discovery run is auditable and honestly sourced.
    slug = body["project"]["slug"]
    status = client.get(f"/api/projects/{slug}/analysis")
    assert status.status_code == 200
    assert status.json()["status"] == "verified"
    assert status.json()["verified_count"] == body["surfaced"]

    curated = client.post("/api/curate-hero", json={"repo_path": str(repo_path)})
    assert curated.status_code == 200
    result = curated.json()
    assert result["revision_sha"] == sha
    assert result["validation"]["target_test_failed"] is True

    topic = client.get(f"/api/topics/{result['topic_id']}")
    assert topic.json()["checkable"] == 1

    check = client.post(f"/api/topics/{result['topic_id']}/checks")
    assert check.status_code == 200
    run = client.post(f"/api/checks/{check.json()['id']}/run")
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
    assert body["project"]["is_demo"] == 0
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
