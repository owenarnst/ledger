import json

import pytest

from backend.repository import (
    HERO_REPO_CHECK,
    LedgerRepository,
    RecipeValidationError,
    RepoCheckSpec,
    TopicNotCheckableError,
)
from backend.ingestion import ClaudeCodeAdapter, CodexAdapter


def test_initialize_does_not_seed_demo(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.initialize()

    assert repo.list_projects() == []


def test_seed_demo_installs_curated_project_and_topics(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.initialize()
    repo.seed_demo()

    projects = repo.list_projects()
    assert [project["slug"] for project in projects] == ["docs-api"]
    assert projects[0]["is_demo"] == 1

    topics = repo.list_topics("docs-api")
    assert len(topics) == 4
    assert topics[0]["state"] == "check_recommended"
    assert "tenant" in topics[0]["title"].lower()
    # Only the fully grounded hero topic carries a curated recipe.
    assert topics[0]["checkable"] == 1
    assert all(topic["checkable"] == 0 for topic in topics[1:])


def test_seed_demo_is_idempotent(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.initialize()
    repo.seed_demo()
    repo.seed_demo()

    assert [project["slug"] for project in repo.list_projects()] == ["docs-api"]
    assert len(repo.list_topics("docs-api")) == 4


def test_seeded_topic_has_revision(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.initialize()
    repo.seed_demo()

    topic = repo.get_topic("tenant-cache-isolation")

    assert topic["current_revision"]["id"] == "tenant-cache-isolation-rev-1"
    assert topic["current_revision"]["topic_id"] == "tenant-cache-isolation"
    assert topic["current_revision"]["revision"] == 1
    assert topic["current_revision"]["commit_sha"] == "demo-seed"
    assert topic["current_revision"]["code_path"] == "retrieval/rerank.py"


def test_seeded_topic_has_session_grounded_claude_receipt(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.initialize()
    repo.seed_demo()

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


def test_check_lifecycle_persists_attempt_and_completion(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()
    repo.seed_demo()

    check = repo.create_check("tenant-cache-isolation")
    assert check["state"] == "in_progress"
    assert check["sandbox_path"]
    assert check["topic_revision_id"] == "tenant-cache-isolation-rev-1"
    # The check runs the recipe's own command, not a hardcoded runner.
    assert check["test_command"] == "python -m pytest tests"

    result = repo.run_check(check["id"])
    assert result["passed"] is False
    assert "test_filters_documents_by_tenant" in result["output"]

    file_state = repo.read_check_file(check["id"], "retrieval/rerank.py")
    assert "return list(documents)" in file_state["content"]

    fixed = file_state["content"].replace(
        "return list(documents)",
        "return [doc for doc in documents if doc.tenant_id == tenant_id]",
    )
    repo.update_check_file(check["id"], "retrieval/rerank.py", fixed)

    result = repo.run_check(check["id"])
    assert result["passed"] is True

    completed = repo.complete_check(check["id"])
    assert completed["state"] == "completed"
    assert completed["run_count"] == 2

    events = repo.list_topic_events("tenant-cache-isolation")
    assert events[-1]["event_type"] == "practiced"
    assert events[-1]["topic_revision_id"] == "tenant-cache-isolation-rev-1"


def test_create_check_refused_when_topic_has_no_recipe(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()
    repo.seed_demo()

    with pytest.raises(TopicNotCheckableError):
        repo.create_check("rerank-threshold")


def test_project_identity_resists_slug_collision_hijack(tmp_path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.initialize()
    repo.seed_demo()  # demo owns slug "docs-api" and repo_path "/demo/docs-api"

    real_repo = tmp_path / "docs-api"
    real_repo.mkdir()
    project = repo.initialize_project_from_repo(str(real_repo))

    # A real repo whose basename collides with the demo gets a distinct slug,
    # and the demo project is never re-homed onto the real path.
    assert project["slug"] != "docs-api"
    assert project["is_demo"] == 0
    assert project["repo_path"] == str(real_repo)
    demo = next(p for p in repo.list_projects() if p["id"] == "project-docs-api")
    assert demo["repo_path"] == "/demo/docs-api"


def test_hook_event_registers_project_without_minting_topics(tmp_path):
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
        payload={
            "changed_files": [
                "retrieval/rerank.py",
                "/etc/passwd",  # absolute, outside the repo
                "../sibling/leak.py",  # escapes the repo
                ".git/config",  # non-source dir
            ]
        },
    )

    project = result["project"]
    assert project["slug"] == "docs-api"
    assert project["repo_path"] == str(repo_path)
    assert project["is_demo"] == 0

    # File activity never becomes a Topic.
    assert result["topics"] == []
    assert repo.list_topics("docs-api") == []

    # Only in-repo paths survive containment filtering.
    payload = json.loads(result["event"]["payload_json"])
    assert payload["changed_files"] == ["retrieval/rerank.py"]


def test_hook_event_labels_provider_on_event_and_session(tmp_path):
    repo_path = tmp_path / "docs-api"
    (repo_path / "retrieval").mkdir(parents=True)
    (repo_path / "retrieval" / "rerank.py").write_text("def rerank():\n    return []\n")

    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    result = repo.record_hook_event(
        event_type="SessionStart",
        cwd=str(repo_path),
        branch="main",
        head_sha="abc123",
        payload={
            "changed_files": ["retrieval/rerank.py"],
            "session_id": "claude-session-x",
            "source_path": "~/.claude/projects/x.jsonl",
        },
    )

    assert result["event"]["provider"] == "claude_code"
    assert result["topics"] == []
    assert repo.get_session("claude-session-x")["provider"] == "claude_code"


def test_hook_event_records_codex_session_provenance(tmp_path):
    repo_path = tmp_path / "docs-api"
    (repo_path / "retrieval").mkdir(parents=True)
    (repo_path / "retrieval" / "rerank.py").write_text("def rerank():\n    return []\n")

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

    assert result["event"]["provider"] == "codex"
    assert result["topics"] == []
    session = repo.get_session("codex-session-1")
    assert session["provider"] == "codex"
    assert session["source_path"] == "~/.codex/sessions/session-1.jsonl"


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


# --------------------------------------------------------------------------- #
# Step 3 — real topic extraction from repository evidence
# --------------------------------------------------------------------------- #

def test_extract_surfaces_untrailed_topics_but_none_checkable(git_repo, tmp_path):
    repo_path, _sha = git_repo
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    result = repo.extract_or_refresh_topics(repo_path)

    assert result["project"]["is_demo"] == 0
    assert result["analysis_source"] == "deterministic"  # CI default analyst
    assert result["surfaced"] >= 1
    assert result["considered"] > result["surfaced"]  # the analyst's gate cut some sites
    topics = result["topics"]
    assert topics
    # Discovery grounds real candidates but never makes one checkable.
    assert all(topic["checkable"] == 0 for topic in topics)
    assert topics[0]["risk_class"] == "persistence"
    assert "tenant" in topics[0]["title"].lower()


def test_extracted_topic_carries_grounded_code_evidence(git_repo, tmp_path):
    repo_path, sha = git_repo
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    result = repo.extract_or_refresh_topics(repo_path)
    hero = repo.get_topic(result["topics"][0]["id"])

    assert hero["current_revision"]["commit_sha"] == sha
    assert hero["current_revision"]["code_path"] == "retrieval/rerank.py"
    kinds = {item["kind"] for item in hero["evidence"]}
    # Grounded code evidence is present; absence ("missing_reasoning") is never
    # promoted into a fact (ADR-0002).
    assert "code" in kinds
    assert "missing_reasoning" not in kinds
    code = next(item for item in hero["evidence"] if item["kind"] == "code")
    assert code["source_path"].startswith("retrieval/rerank.py:")
    assert "tenant_id" in code["body"]


def test_extract_is_idempotent_and_revisions_stay_immutable(git_repo, tmp_path):
    repo_path, _sha = git_repo
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    first = repo.extract_or_refresh_topics(repo_path)
    second = repo.extract_or_refresh_topics(repo_path)

    assert len(first["topics"]) == len(second["topics"])
    for topic in second["topics"]:
        # Unchanged code never spawns a second revision.
        assert repo.get_topic(topic["id"])["current_revision"]["revision"] == 1


def test_code_change_creates_a_new_revision(git_repo, tmp_path):
    repo_path, _sha = git_repo
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()
    first = repo.extract_or_refresh_topics(repo_path)
    hero_id = first["topics"][0]["id"]

    rerank = repo_path / "retrieval" / "rerank.py"
    rerank.write_text(
        rerank.read_text().replace(
            "return [doc for doc in documents if doc.tenant_id == tenant_id]",
            "scoped = [doc for doc in documents if doc.tenant_id == tenant_id]\n    return scoped",
        )
    )

    repo.extract_or_refresh_topics(repo_path)

    assert repo.get_topic(hero_id)["current_revision"]["revision"] == 2


def test_extract_records_an_auditable_analysis_run(git_repo, tmp_path):
    repo_path, _sha = git_repo
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    result = repo.extract_or_refresh_topics(repo_path)
    status = repo.get_analysis_status(result["project"]["slug"])

    assert status["status"] == "verified"
    assert status["analysis_source"] == "deterministic"
    assert status["verified_count"] == result["surfaced"]
    assert status["proposed_count"] >= status["verified_count"]
    assert status["schema_version"]  # the prompt/contract version is recorded


def test_analysis_unavailable_falls_back_to_last_verified_worklist(git_repo, tmp_path):
    from backend.analyst import DiscoveryResult

    class _UnavailableAnalyst:
        model_id = "claude-code"

        def discover(self, repo_path, index):
            return DiscoveryResult([], self.model_id)  # nothing verifiable this run

    repo_path, _sha = git_repo
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    first = repo.extract_or_refresh_topics(repo_path)  # deterministic -> verified
    assert first["surfaced"] >= 1

    second = repo.extract_or_refresh_topics(repo_path, analyst=_UnavailableAnalyst())

    # The prior worklist is retained, never wiped, and is honestly labelled.
    assert second["surfaced"] == 0
    assert second["analysis_source"] == "last_verified"
    slug = first["project"]["slug"]
    assert len(repo.list_topics(slug)) == len(first["topics"])
    assert repo.get_analysis_status(slug)["analysis_source"] == "last_verified"


def test_extracted_topic_exposes_derived_display_facts(git_repo, tmp_path):
    repo_path, _sha = git_repo
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    result = repo.extract_or_refresh_topics(repo_path)
    hero = result["topics"][0]

    # Derived, not model claims: status from lifecycle, impact from risk, summary
    # from accepted counts.
    assert hero["ownership_status"] == "Check recommended"
    assert hero["impact_level"] == "high"  # persistence path
    assert hero["evidence_summary"].startswith("1 code anchor")

    detail = repo.get_topic(hero["id"])
    assert detail["code_anchors"] and detail["code_anchors"][0]["kind"] == "code"
    assert detail["code_anchors"][0]["excerpt_sha"]
    assert all(item["kind"] != "missing_reasoning" for item in detail["evidence"])


def test_ingestion_does_not_mint_topics_even_after_extraction(git_repo, tmp_path):
    # Extraction is the only topic source, and it is explicit. A hook event for
    # an already-extracted repo reports existing topics but mints nothing new.
    repo_path, _sha = git_repo
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()
    repo.extract_or_refresh_topics(repo_path)
    before = len(repo.list_topics(repo.list_projects()[0]["slug"]))

    repo.record_hook_event(event_type="post-commit", cwd=str(repo_path), head_sha="deadbeef")

    after = len(repo.list_topics(repo.list_projects()[0]["slug"]))
    assert after == before


# --------------------------------------------------------------------------- #
# Step 2 — curated repo-derived check, gated on baseline-green -> mutant-red
# --------------------------------------------------------------------------- #

def test_curate_hero_validates_and_makes_one_topic_checkable(git_repo, tmp_path):
    repo_path, sha = git_repo
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    result = repo.install_repo_check_recipe(repo_path)

    assert result["revision_sha"] == sha
    assert result["validation"] == {
        "baseline_passed": True,
        "mutant_failed": True,
        "target_test_failed": True,
    }
    hero = repo.get_topic(result["topic_id"])
    assert hero["checkable"] == 1
    assert hero["title"] == "Tenant isolation in retrieval"
    # Exactly one topic is checkable; the rest remain curation candidates.
    topics = repo.list_topics(result["project"]["slug"])
    assert [t["checkable"] for t in topics].count(1) == 1


def test_curated_repo_check_runs_red_at_pinned_revision_then_green(git_repo, tmp_path):
    repo_path, _sha = git_repo
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()
    result = repo.install_repo_check_recipe(repo_path)

    check = repo.create_check(result["topic_id"])
    assert check["test_command"] == "python -m pytest tests"

    red = repo.run_check(check["id"])
    assert red["passed"] is False
    assert "test_search_never_returns_another_tenants_documents" in red["output"]

    state = repo.read_check_file(check["id"], "retrieval/rerank.py")
    repo.update_check_file(
        check["id"],
        "retrieval/rerank.py",
        state["content"].replace(
            "return list(documents)",
            "return [doc for doc in documents if doc.tenant_id == tenant_id]",
        ),
    )
    green = repo.run_check(check["id"])
    assert green["passed"] is True


def test_curate_refuses_a_recipe_that_does_not_turn_red(git_repo, tmp_path):
    repo_path, _sha = git_repo
    repo = LedgerRepository(tmp_path / "ledger.db", sandbox_root=tmp_path / "sandboxes")
    repo.initialize()

    # A no-op "mutation" leaves the suite green, so the recipe is untrustworthy.
    no_op = RepoCheckSpec(
        file=HERO_REPO_CHECK.file,
        symbol=HERO_REPO_CHECK.symbol,
        target_file=HERO_REPO_CHECK.target_file,
        test_command=HERO_REPO_CHECK.test_command,
        target_test=HERO_REPO_CHECK.target_test,
        mutation_before=HERO_REPO_CHECK.mutation_before,
        mutation_after=HERO_REPO_CHECK.mutation_before,
    )

    with pytest.raises(RecipeValidationError):
        repo.install_repo_check_recipe(repo_path, spec=no_op)

    # The topic stays a non-checkable candidate; nothing was persisted.
    topic_id = repo._topic_id_for(
        repo.list_projects()[0]["slug"], no_op.file, no_op.symbol
    )
    assert repo.get_topic(topic_id)["checkable"] == 0
