from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .analyst import (
    ANALYSIS_SCHEMA_VERSION,
    Analyst,
    AnalystIndex,
    DiscoveryResult,
    TraceLocator,
    create_analyst,
)
from .coach import Coach, create_coach
from .db import connect, initialize_schema
from .extraction import resolve_head_sha
from .ingestion import DEFAULT_PROVIDER, IngestionEvent, adapter_for
from .sandbox import create_sandbox_from_recipe, run_test_command, validate_recipe
from .verifier import VerificationResult, VerifiedTopic, verify_proposals


DEFAULT_DB_PATH = Path.home() / ".ledger" / "ledger.db"
DEFAULT_SANDBOX_ROOT = Path.home() / ".ledger" / "sandboxes"

DEMO_PROJECT_ID = "project-docs-api"

# Directories whose contents are never repository decision sites, even when a
# transcript's tool call touched a file inside them.
NON_REPO_DIR_PARTS = frozenset(
    {".git", ".venv", "venv", "node_modules", ".claude", "__pycache__", ".pytest_cache"}
)


class TopicNotCheckableError(Exception):
    """Raised when a Check is requested for a Topic that has no curated recipe."""


class RecipeValidationError(Exception):
    """Raised when a repo-derived recipe fails baseline-green -> mutant-red."""


@dataclass(frozen=True)
class RepoCheckSpec:
    """A curated, disclosed spec for one repo-derived check.

    It pins a real decision anchor, a curated substring mutation, the test
    command, and the test that mutation must turn red. ``revision_sha=None``
    means "pin the repository's current HEAD at install time" — the recipe is
    immutable once installed, but install isn't brittle to a hardcoded SHA.
    """

    file: str
    symbol: str
    target_file: str
    test_command: str
    target_test: str
    mutation_before: str
    mutation_after: str
    title: str | None = None
    summary: str | None = None
    invariant: str | None = None
    revision_sha: str | None = None


# The one curated repo-derived check (Step 2). Tenant isolation in the docs
# search pipeline: drop the tenant filter and the cross-tenant test goes red.
HERO_REPO_CHECK = RepoCheckSpec(
    file="retrieval/rerank.py",
    symbol="visible_documents_for_tenant",
    target_file="retrieval/rerank.py",
    test_command="python -m pytest tests",
    target_test="tests/test_pipeline.py::test_search_never_returns_another_tenants_documents",
    mutation_before="return [doc for doc in documents if doc.tenant_id == tenant_id]",
    mutation_after="return list(documents)",
    title="Tenant isolation in retrieval",
    summary=(
        "Retrieval candidates must be scoped to the requesting tenant before "
        "ranking, so one tenant can never see another tenant's documents."
    ),
    invariant=(
        "visible_documents_for_tenant must filter candidates down to the "
        "requesting tenant before they are ranked and returned."
    ),
)


# Derived display facts (ADR-0002): not model claims. Ownership status comes from
# the persisted lifecycle; impact level falls back to risk-class when the analyst
# did not supply one; the evidence summary is computed from accepted counts.
_OWNERSHIP_STATUS = {
    "check_recommended": "Check recommended",
    "in_progress": "In progress",
    "practiced": "Practiced",
    "code_changed_since_practice": "Code changed since practice",
    "revisit_suggested": "Revisit suggested",
}
_IMPACT_BY_RISK = {
    "persistence": "high",
    "external_api": "high",
    "ranking": "medium",
    "retrieval": "medium",
    "general": "low",
}
_PROVIDER_LABEL = {"claude_code": "Claude", "codex": "Codex"}


def _ownership_status(state: str) -> str:
    return _OWNERSHIP_STATUS.get(state, state.replace("_", " ").capitalize())


def _provider_label(provider: str | None) -> str:
    return _PROVIDER_LABEL.get(provider or "", (provider or "session").replace("_", " ").title())


def _is_trace_evidence(kind: str) -> bool:
    return kind == "trace" or kind.endswith("_receipt")


class LedgerRepository:
    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        sandbox_root: Path = DEFAULT_SANDBOX_ROOT,
        coach: Coach | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.sandbox_root = Path(sandbox_root)
        self.coach = coach or create_coach()

    def initialize(self) -> None:
        """Prepare the schema only. Demo content is never seeded implicitly."""
        with connect(self.db_path) as conn:
            initialize_schema(conn)

    def initialize_schema(self) -> None:
        with connect(self.db_path) as conn:
            initialize_schema(conn)

    def seed_demo(self) -> dict[str, Any]:
        """Explicitly install the curated demo project. Idempotent."""
        with connect(self.db_path) as conn:
            initialize_schema(conn)
            if not conn.execute(
                "SELECT 1 FROM projects WHERE id = ?", (DEMO_PROJECT_ID,)
            ).fetchone():
                self._seed_demo(conn)
            return dict(
                conn.execute("SELECT * FROM projects WHERE id = ?", (DEMO_PROJECT_ID,)).fetchone()
            )

    # Backwards-compatible alias.
    def seed_demo_data(self) -> dict[str, Any]:
        return self.seed_demo()

    def list_projects(self) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            return self._rows(conn.execute("SELECT * FROM projects ORDER BY created_at"))

    def list_all_topics(self) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM topics ORDER BY rank").fetchall()
            return [self._decorate_topic(conn, row) for row in rows]

    def list_topics(self, project_slug: str) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT topics.*
                FROM topics
                JOIN projects ON projects.id = topics.project_id
                WHERE projects.slug = ?
                ORDER BY topics.rank
                """,
                (project_slug,),
            ).fetchall()
            return [self._decorate_topic(conn, row) for row in rows]

    def initialize_project_from_repo(
        self,
        repo_path: str | Path,
        *,
        name: str | None = None,
    ) -> dict[str, Any]:
        path = Path(repo_path).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise ValueError(f"repository path does not exist: {repo_path}")

        with connect(self.db_path) as conn:
            # Identity is the resolved repo path. A project is never re-homed to a
            # different path, so a basename/slug collision can't hijack another repo.
            existing = conn.execute(
                "SELECT * FROM projects WHERE repo_path = ?", (str(path),)
            ).fetchone()
            if existing:
                if name and name != existing["name"]:
                    conn.execute(
                        "UPDATE projects SET name = ? WHERE id = ?", (name, existing["id"])
                    )
                    conn.commit()
                return dict(
                    conn.execute(
                        "SELECT * FROM projects WHERE id = ?", (existing["id"],)
                    ).fetchone()
                )

            slug = self._unique_slug(conn, name or path.name)
            project_id = f"project-{slug}"
            conn.execute(
                "INSERT INTO projects (id, slug, name, repo_path, is_demo) VALUES (?, ?, ?, ?, 0)",
                (project_id, slug, name or path.name, str(path)),
            )
            conn.commit()
            return dict(
                conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            )

    def record_hook_event(
        self,
        *,
        event_type: str,
        cwd: str | Path,
        branch: str | None = None,
        head_sha: str | None = None,
        payload: dict[str, Any] | None = None,
        provider: str = DEFAULT_PROVIDER,
    ) -> dict[str, Any]:
        """Record provenance (session + hook event) for repository activity.

        Ingestion never mints Topics. Changed files are containment-filtered to
        this repository so cross-repo and temp-file noise never enters the ledger.
        """
        project = self.initialize_project_from_repo(cwd)
        repo_path = Path(project["repo_path"])
        payload = dict(payload or {})
        payload["changed_files"] = self._contained_repo_files(
            repo_path, payload.get("changed_files") or []
        )
        event = IngestionEvent(
            provider=provider,
            event_type=event_type,
            cwd=str(cwd),
            branch=branch,
            head_sha=head_sha,
            payload=payload,
        )
        with connect(self.db_path) as conn:
            self._upsert_session(conn, project["id"], event)
            if head_sha:
                conn.execute(
                    "INSERT INTO commits (sha, project_id) VALUES (?, ?) ON CONFLICT(sha) DO NOTHING",
                    (head_sha, project["id"]),
                )
            cursor = conn.execute(
                """
                INSERT INTO hook_events (project_id, provider, event_type, branch, head_sha, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project["id"],
                    event.provider,
                    event.event_type,
                    event.branch,
                    event.head_sha,
                    json.dumps(event.payload, sort_keys=True),
                ),
            )
            conn.commit()
            stored_event = dict(
                conn.execute("SELECT * FROM hook_events WHERE id = ?", (cursor.lastrowid,)).fetchone()
            )

        return {
            "project": project,
            "event": stored_event,
            "topics": self.list_topics(project["slug"]),
        }

    def import_provider_sessions(self, provider: str, root: str | Path) -> dict[str, Any]:
        adapter = adapter_for(provider)
        events = adapter.read_sessions(root)
        imported: list[dict[str, Any]] = []
        last_slug: str | None = None
        for event in events:
            result = self.record_hook_event(
                provider=event.provider,
                event_type=event.event_type,
                cwd=event.cwd,
                branch=event.branch,
                head_sha=event.head_sha,
                payload=event.payload,
            )
            imported.append(result["event"])
            last_slug = result["project"]["slug"]
        return {
            "provider": provider,
            "imported": len(imported),
            "events": imported,
            "topics": self.list_topics(last_slug) if last_slug else [],
        }

    # ------------------------------------------------------------------ #
    # Topic extraction (Step 3) — deterministic evidence pipeline
    # ------------------------------------------------------------------ #

    def extract_or_refresh_topics(
        self,
        repo_path: str | Path,
        *,
        analyst: Analyst | None = None,
    ) -> dict[str, Any]:
        """Derive the worklist via agentic discovery, persisting grounded topics.

        Per ADR-0002 the Topic Analyst (Claude Code, or the deterministic
        fallback) decides worklist membership and order; deterministic code only
        seeds a recall index and resolves the analyst's cited locators before
        persisting. The repository layer no longer gates or ranks. Re-running is
        idempotent: a topic gains a new immutable revision only when the code its
        primary anchor cites changes fingerprint.
        """
        project = self.initialize_project_from_repo(repo_path)
        repo_root = Path(project["repo_path"])
        analyst = analyst or create_analyst()
        head_sha = resolve_head_sha(repo_root)

        index = AnalystIndex.from_repo(repo_root, traces=self._trace_locators(project))
        discovery = analyst.discover(repo_root, index)
        verification = verify_proposals(
            discovery.proposals, repo_root=repo_root, index=index, available_traces=index.traces
        )
        input_scope = {
            "repo_path": project["repo_path"],
            "head_sha": head_sha,
            "candidate_count": len(index.candidates),
            "trace_count": len(index.traces),
        }

        persisted: list[str] = []
        with connect(self.db_path) as conn:
            existing_topics = conn.execute(
                "SELECT COUNT(*) AS n FROM topics WHERE project_id = ?", (project["id"],)
            ).fetchone()["n"]
            for rank, verified in enumerate(verification.verified, start=1):
                persisted.append(self._persist_verified_topic(conn, project, verified, rank, head_sha))

            if verification.verified:
                status, analysis_source = "verified", discovery.model_id
            elif existing_topics:
                # Fallback: never wipe — retain the last verified worklist.
                status, analysis_source = "empty", "last_verified"
            else:
                status, analysis_source = "empty", "pending"

            self._record_analysis_run(conn, project, discovery, verification, status, input_scope)
            conn.commit()

        return {
            "project": project,
            "head_sha": head_sha,
            "analysis_source": analysis_source,
            "considered": len(index.candidates),
            "surfaced": len(persisted),
            "rejected": len(verification.rejected),
            "topics": self.list_topics(project["slug"]),
        }

    def _record_analysis_run(
        self, conn: Any, project: dict[str, Any], discovery: DiscoveryResult,
        verification: VerificationResult, status: str, input_scope: dict[str, Any],
    ) -> None:
        rejected = [{"title": r.title, "reason": r.reason} for r in verification.rejected]
        conn.execute(
            """
            INSERT INTO analysis_runs
            (project_id, analyst_model, schema_version, input_scope_json, raw_output,
             proposed_count, verified_count, rejected_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project["id"], discovery.model_id, ANALYSIS_SCHEMA_VERSION,
             json.dumps(input_scope), discovery.raw_output,
             len(discovery.proposals), len(verification.verified),
             json.dumps(rejected), status),
        )

    def _trace_locators(self, project: dict[str, Any]) -> tuple[TraceLocator, ...]:
        """Development traces the analyst is allowed to cite (recall material)."""
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, provider, source_path FROM sessions WHERE project_id = ? ORDER BY id",
                (project["id"],),
            ).fetchall()
        return tuple(
            TraceLocator(provider=r["provider"], session_id=r["id"], source_path=r["source_path"])
            for r in rows
        )

    def _persist_verified_topic(
        self, conn: Any, project: dict[str, Any], verified: VerifiedTopic, rank: int,
        head_sha: str | None,
    ) -> str:
        """Persist one verified topic: immutable revision + grouped evidence.

        Topic identity rides the primary verified anchor's file+symbol; a new
        immutable revision is minted only when the accepted excerpt's hash
        changes. Grouped Code-anchor and Development-trace evidence carry the
        verifier's excerpt hash, relevance, and link confidence. No
        ``missing_reasoning`` evidence is emitted — absence is never a fact.
        """
        primary = verified.primary
        proposal = verified.proposal
        topic_id = self._topic_id_for(project["slug"], primary.path, primary.symbol)

        latest = self._current_revision(conn, topic_id)
        if latest is None:
            revision_number, new_revision = 1, True
        elif latest["fingerprint"] != verified.fingerprint:
            revision_number, new_revision = latest["revision"] + 1, True
        else:
            revision_number, new_revision = latest["revision"], False

        existing = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO topics
                (id, project_id, provider, title, state, summary, why_now,
                 risk_class, caller_count, claude_authored, checkable, rank,
                 impact_level, impact_consequence, priority_rationale)
                VALUES (?, ?, 'claude_code', ?, 'check_recommended', ?, ?, ?, ?, 0, 0, ?, ?, ?, ?)
                """,
                (topic_id, project["id"], proposal.title, proposal.maintenance_obligation,
                 proposal.priority_rationale, primary.risk_class, primary.caller_count, rank,
                 proposal.impact_level, proposal.impact_consequence, proposal.priority_rationale),
            )
            conn.execute(
                "INSERT INTO topic_events (topic_id, event_type, body) VALUES (?, 'created', ?)",
                (topic_id, f"Proposed from {primary.source_locator}"),
            )
        else:
            # Refresh display facts/rank; preserve curated checkability and
            # lifecycle. A code change under a practiced topic re-surfaces it.
            new_state = existing["state"]
            if new_revision and existing["state"] == "practiced":
                new_state = "code_changed_since_practice"
            conn.execute(
                """
                UPDATE topics SET title = ?, summary = ?, why_now = ?, risk_class = ?,
                       caller_count = ?, rank = ?, state = ?,
                       impact_level = ?, impact_consequence = ?, priority_rationale = ?
                WHERE id = ?
                """,
                (proposal.title, proposal.maintenance_obligation, proposal.priority_rationale,
                 primary.risk_class, primary.caller_count, rank, new_state,
                 proposal.impact_level, proposal.impact_consequence, proposal.priority_rationale,
                 topic_id),
            )

        if not new_revision:
            return topic_id

        revision_id = f"{topic_id}-rev-{revision_number}"
        conn.execute(
            """
            INSERT INTO topic_revisions
            (id, topic_id, revision, commit_sha, code_path, invariant, risk_class, fingerprint)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (revision_id, topic_id, revision_number, head_sha, primary.path,
             proposal.invariant, primary.risk_class, verified.fingerprint),
        )
        for anchor in verified.anchors:
            code_eid = conn.execute(
                """
                INSERT INTO evidence
                (topic_id, provider, session_id, source_path, tool_sequence_json,
                 link_confidence, kind, title, body, excerpt_sha, relevance)
                VALUES (?, 'claude_code', NULL, ?, '[]', 'exact', 'code', ?, ?, ?, ?)
                """,
                (topic_id, anchor.source_locator, anchor.source_locator, anchor.excerpt,
                 anchor.excerpt_sha, anchor.relevance),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO revision_evidence (topic_revision_id, evidence_id, role, confidence)
                VALUES (?, ?, 'code', 'exact')
                """,
                (revision_id, code_eid),
            )
        for trace in verified.traces:
            trace_eid = conn.execute(
                """
                INSERT INTO evidence
                (topic_id, provider, session_id, source_path, tool_sequence_json,
                 link_confidence, kind, title, body, excerpt_sha, relevance)
                VALUES (?, ?, ?, ?, '[]', ?, 'trace', ?, ?, NULL, ?)
                """,
                (topic_id, trace.provider, trace.session_id, trace.source_path,
                 trace.link_confidence, f"{trace.provider} session", trace.relevance, trace.relevance),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO revision_evidence (topic_revision_id, evidence_id, role, confidence)
                VALUES (?, ?, 'trace', ?)
                """,
                (revision_id, trace_eid, trace.link_confidence),
            )
        if existing is not None:
            conn.execute(
                """
                INSERT INTO topic_events (topic_id, topic_revision_id, event_type, body)
                VALUES (?, ?, 'code_changed', ?)
                """,
                (topic_id, revision_id, f"Code changed at {primary.path}"),
            )
        return topic_id

    def _topic_id_for(self, project_slug: str, file: str, symbol: str) -> str:
        return self._slugify(f"{project_slug}-{Path(file).stem}-{symbol}")

    # ------------------------------------------------------------------ #
    # Curated repo-derived check (Step 2)
    # ------------------------------------------------------------------ #

    def install_repo_check_recipe(
        self,
        repo_path: str | Path,
        *,
        spec: RepoCheckSpec = HERO_REPO_CHECK,
        analyst: Analyst | None = None,
    ) -> dict[str, Any]:
        """Curate one repo-derived check, gated on baseline-green -> mutant-red.

        Discovery must have surfaced the spec's anchor as a real topic; this
        pins a real revision, proves the curated mutation turns the targeted
        test red against a green baseline, and only then persists the recipe and
        flips the topic to checkable. The mutation is curated and disclosed —
        nothing here is auto-generated.
        """
        extraction = self.extract_or_refresh_topics(repo_path, analyst=analyst)
        project = extraction["project"]
        repo_root = Path(project["repo_path"])
        topic_id = self._topic_id_for(project["slug"], spec.file, spec.symbol)

        with connect(self.db_path) as conn:
            topic = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
        if topic is None:
            raise RecipeValidationError(
                f"no extracted topic for {spec.file}::{spec.symbol}; cannot curate a check"
            )

        revision_sha = spec.revision_sha or resolve_head_sha(repo_root)
        if not revision_sha:
            raise RecipeValidationError(
                f"{repo_root} is not a git repository; cannot pin a revision"
            )

        validation = validate_recipe(
            fixture_source="@repo",
            repo_path=repo_root,
            revision_sha=revision_sha,
            target_file=spec.target_file,
            test_command=spec.test_command,
            mutation_before=spec.mutation_before,
            mutation_after=spec.mutation_after,
            target_test=spec.target_test,
        )
        if not validation.ok:
            raise RecipeValidationError(
                "recipe failed baseline-green -> mutant-red validation "
                f"(baseline_passed={validation.baseline_passed}, "
                f"mutant_failed={validation.mutant_failed}, "
                f"target_test_failed={validation.target_test_failed})"
            )

        with connect(self.db_path) as conn:
            revision = self._current_revision(conn, topic_id)
            revision_id = revision["id"] if revision else None
            # Curated, disclosed overrides for the demo hero's interpretation.
            if spec.title:
                conn.execute(
                    "UPDATE topics SET title = ?, summary = ? WHERE id = ?",
                    (spec.title, spec.summary or topic["summary"], topic_id),
                )
            if spec.invariant and revision_id:
                conn.execute(
                    "UPDATE topic_revisions SET invariant = ? WHERE id = ?",
                    (spec.invariant, revision_id),
                )
            conn.execute("UPDATE topics SET checkable = 1 WHERE id = ?", (topic_id,))
            conn.execute("DELETE FROM check_recipes WHERE topic_id = ?", (topic_id,))
            conn.execute(
                """
                INSERT INTO check_recipes
                (id, topic_id, topic_revision_id, fixture_source, revision_sha,
                 target_file, target_test, test_command, mutation_before, mutation_after)
                VALUES (?, ?, ?, '@repo', ?, ?, ?, ?, ?, ?)
                """,
                (f"recipe-{topic_id}", topic_id, revision_id, revision_sha,
                 spec.target_file, spec.target_test, spec.test_command,
                 spec.mutation_before, spec.mutation_after),
            )
            conn.execute(
                """
                INSERT INTO topic_events (topic_id, topic_revision_id, event_type, body)
                VALUES (?, ?, 'check_curated', ?)
                """,
                (topic_id, revision_id, f"Curated repo-derived check pinned at {revision_sha[:12]}"),
            )
            conn.commit()

        return {
            "project": project,
            "topic_id": topic_id,
            "revision_sha": revision_sha,
            "validation": {
                "baseline_passed": validation.baseline_passed,
                "mutant_failed": validation.mutant_failed,
                "target_test_failed": validation.target_test_failed,
            },
        }

    def get_topic(self, topic_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            topic = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
            if not topic:
                raise KeyError(topic_id)
            payload = self._decorate_topic(conn, topic)
            revision = self._current_revision(conn, topic_id)
            payload["current_revision"] = dict(revision) if revision else None
            evidence = self._evidence_rows(
                conn.execute(
                    """
                    SELECT provider, session_id, source_path, tool_sequence_json,
                           link_confidence, kind, title, body, excerpt_sha, relevance
                    FROM evidence
                    WHERE topic_id = ?
                    """,
                    (topic_id,),
                )
            )
            # Drop the retired "missing_reasoning" — a computed absence is never a
            # fact (ADR-0002). Group the rest for the expanded view.
            evidence = [item for item in evidence if item["kind"] != "missing_reasoning"]
            payload["evidence"] = evidence
            payload["code_anchors"] = [item for item in evidence if item["kind"] == "code"]
            payload["development_traces"] = [
                item for item in evidence if _is_trace_evidence(item["kind"])
            ]
            return payload

    def _decorate_topic(self, conn: Any, topic: Any) -> dict[str, Any]:
        """Add derived display facts: ownership status, impact level, evidence summary."""
        payload = dict(topic)
        payload["ownership_status"] = _ownership_status(payload["state"])
        payload["impact_level"] = payload.get("impact_level") or _IMPACT_BY_RISK.get(
            payload["risk_class"], "low"
        )
        payload["evidence_summary"] = self._evidence_summary(conn, payload["id"])
        return payload

    def _evidence_summary(self, conn: Any, topic_id: str) -> str:
        """Compact verified grounding, e.g. ``3 code anchors · 2 related Claude sessions``."""
        rows = conn.execute(
            "SELECT kind, provider FROM evidence WHERE topic_id = ?", (topic_id,)
        ).fetchall()
        code = sum(1 for row in rows if row["kind"] == "code")
        traces = [row for row in rows if _is_trace_evidence(row["kind"])]
        parts = [f"{code} code anchor{'' if code == 1 else 's'}"]
        if traces:
            label = _provider_label(traces[0]["provider"])
            count = len(traces)
            parts.append(f"{count} related {label} session{'' if count == 1 else 's'}")
        return " · ".join(parts)

    def get_analysis_status(self, project_slug: str) -> dict[str, Any]:
        """The latest discovery run's verdict + the honest worklist source.

        ``analysis_source`` is ``claude-code``/``deterministic`` after a verified
        run, ``last_verified`` when the latest run produced nothing but prior
        topics remain, and ``pending`` when nothing has been verified yet.
        """
        with connect(self.db_path) as conn:
            project = conn.execute(
                "SELECT * FROM projects WHERE slug = ?", (project_slug,)
            ).fetchone()
            if not project:
                raise KeyError(project_slug)
            run = conn.execute(
                "SELECT * FROM analysis_runs WHERE project_id = ? ORDER BY id DESC LIMIT 1",
                (project["id"],),
            ).fetchone()
            topic_count = conn.execute(
                "SELECT COUNT(*) AS n FROM topics WHERE project_id = ?", (project["id"],)
            ).fetchone()["n"]

        if run is None:
            return {
                "analysis_source": "last_verified" if topic_count else "pending",
                "status": "none",
                "proposed_count": 0,
                "verified_count": topic_count,
                "rejected": [],
            }
        if run["status"] == "verified":
            source = run["analyst_model"]
        else:
            source = "last_verified" if topic_count else "pending"
        return {
            "analysis_source": source,
            "status": run["status"],
            "analyst_model": run["analyst_model"],
            "schema_version": run["schema_version"],
            "proposed_count": run["proposed_count"],
            "verified_count": run["verified_count"],
            "rejected": json.loads(run["rejected_json"]),
            "created_at": run["created_at"],
        }

    def get_session(self, session_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not session:
                raise KeyError(session_id)
            return dict(session)

    def create_check(self, topic_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            topic = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
            if not topic:
                raise KeyError(topic_id)
            recipe = conn.execute(
                "SELECT * FROM check_recipes WHERE topic_id = ?", (topic_id,)
            ).fetchone()
            if not recipe:
                raise TopicNotCheckableError(topic_id)
            revision = self._current_revision(conn, topic_id)
            if not revision:
                raise KeyError(topic_id)
            recipe = dict(recipe)
            revision_id = revision["id"]
            project_row = conn.execute(
                "SELECT repo_path FROM projects WHERE id = ?", (topic["project_id"],)
            ).fetchone()
            repo_path = project_row["repo_path"] if project_row else None

        check_id = uuid.uuid4().hex
        sandbox_path = self.sandbox_root / check_id
        # A pinned revision_sha selects the repo-derived (git) path; otherwise the
        # bundled fixture is copied. repo_path is ignored on the fixture path.
        create_sandbox_from_recipe(
            sandbox_path,
            fixture_source=recipe["fixture_source"],
            target_file=recipe["target_file"],
            mutation_before=recipe["mutation_before"],
            mutation_after=recipe["mutation_after"],
            repo_path=repo_path,
            revision_sha=recipe.get("revision_sha"),
        )
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO checks (id, topic_id, topic_revision_id, state, sandbox_path, target_file, test_command)
                VALUES (?, ?, ?, 'in_progress', ?, ?, ?)
                """,
                (
                    check_id,
                    topic_id,
                    revision_id,
                    str(sandbox_path),
                    recipe["target_file"],
                    recipe["test_command"],
                ),
            )
            conn.execute("UPDATE topics SET state = 'in_progress' WHERE id = ?", (topic_id,))
            conn.execute(
                """
                INSERT INTO topic_events (topic_id, topic_revision_id, event_type, body)
                VALUES (?, ?, 'check_started', ?)
                """,
                (topic_id, revision_id, check_id),
            )
            conn.commit()
        return self.get_check(check_id)

    def get_check(self, check_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            check = conn.execute("SELECT * FROM checks WHERE id = ?", (check_id,)).fetchone()
            if not check:
                raise KeyError(check_id)
            payload = dict(check)
            payload["run_count"] = conn.execute(
                "SELECT COUNT(*) FROM attempts WHERE check_id = ?", (check_id,)
            ).fetchone()[0]
            return payload

    def read_check_file(self, check_id: str, relative_path: str) -> dict[str, str]:
        path = self._check_file_path(check_id, relative_path)
        return {"path": relative_path, "content": path.read_text()}

    def update_check_file(self, check_id: str, relative_path: str, content: str) -> dict[str, str]:
        path = self._check_file_path(check_id, relative_path)
        path.write_text(content)
        return {"path": relative_path, "content": content}

    def _check_file_path(self, check_id: str, relative_path: str) -> Path:
        check = self.get_check(check_id)
        root = Path(check["sandbox_path"]).resolve()
        path = (root / relative_path).resolve()
        if root not in path.parents and path != root:
            raise ValueError("path escapes sandbox")
        if not path.exists():
            raise FileNotFoundError(relative_path)
        return path

    def run_check(self, check_id: str) -> dict[str, Any]:
        check = self.get_check(check_id)
        try:
            result = run_test_command(Path(check["sandbox_path"]), check["test_command"])
            passed = result.passed
            output = result.output
            elapsed_ms = result.elapsed_ms
        except Exception as exc:
            passed = False
            output = f"Check runner failed: {exc}"
            elapsed_ms = 0
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO attempts (check_id, passed, output, elapsed_ms) VALUES (?, ?, ?, ?)",
                (check_id, int(passed), output, elapsed_ms),
            )
            conn.commit()
        return {
            "check_id": check_id,
            "passed": passed,
            "output": output,
            "elapsed_ms": elapsed_ms,
        }

    def complete_check(self, check_id: str, reflection: dict[str, str] | None = None) -> dict[str, Any]:
        check = self.get_check(check_id)
        with connect(self.db_path) as conn:
            conn.execute(
                "UPDATE checks SET state = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (check_id,),
            )
            conn.execute("UPDATE topics SET state = 'practiced' WHERE id = ?", (check["topic_id"],))
            conn.execute(
                """
                INSERT INTO topic_events (topic_id, topic_revision_id, event_type, body)
                VALUES (?, ?, 'practiced', ?)
                """,
                (check["topic_id"], check["topic_revision_id"], check_id),
            )
            if reflection:
                conn.execute(
                    """
                    INSERT INTO reflections
                    (check_id, topic_id, topic_revision_id, invariant, rationale, future_risk)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        check_id,
                        check["topic_id"],
                        check["topic_revision_id"],
                        reflection.get("invariant", ""),
                        reflection.get("rationale", ""),
                        reflection.get("future_risk", ""),
                    ),
                )
            conn.commit()
        return self.get_check(check_id)

    def list_topic_events(self, topic_id: str) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            return self._rows(
                conn.execute(
                    "SELECT * FROM topic_events WHERE topic_id = ? ORDER BY id",
                    (topic_id,),
                )
            )

    def list_reflections(self, topic_id: str) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            return self._rows(
                conn.execute(
                    """
                    SELECT *
                    FROM reflections
                    WHERE topic_id = ?
                    ORDER BY id DESC
                    """,
                    (topic_id,),
                )
            )

    def ask_coach(self, check_id: str, question: str, provider: str | None = None) -> dict[str, str]:
        check = self.get_check(check_id)
        topic = self.get_topic(check["topic_id"])
        latest = self._latest_attempt_output(check_id)
        coach = create_coach(provider) if provider else self.coach
        response = coach.ask(
            topic_title=topic["title"],
            task=topic["summary"],
            test_output=latest,
            question=question,
        )
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO coach_messages (check_id, question, response) VALUES (?, ?, ?)",
                (check_id, question, response),
            )
            conn.commit()
        return {"question": question, "provider": provider or "default", "response": response}

    def _latest_attempt_output(self, check_id: str) -> str:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT output FROM attempts WHERE check_id = ? ORDER BY id DESC LIMIT 1",
                (check_id,),
            ).fetchone()
            return row["output"] if row else "No check has been run yet."

    @staticmethod
    def _contained_repo_files(repo_path: Path, changed_files: Any) -> list[str]:
        """Keep only the changed files that live strictly inside ``repo_path``.

        Absolute paths from a transcript that point outside this repo (other
        repos, ``/var/folders`` temp files) are dropped, as are paths inside
        well-known non-source directories. Returns repo-relative paths.
        """
        if not isinstance(changed_files, list):
            return []
        root = repo_path.expanduser().resolve()
        kept: list[str] = []
        seen: set[str] = set()
        for raw in changed_files:
            if not isinstance(raw, str) or not raw or raw.endswith("/"):
                continue
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = root / candidate
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved != root and root not in resolved.parents:
                continue
            try:
                relative = resolved.relative_to(root)
            except ValueError:
                continue
            if NON_REPO_DIR_PARTS.intersection(relative.parts):
                continue
            text = str(relative)
            if text not in seen:
                seen.add(text)
                kept.append(text)
        return kept

    @staticmethod
    def _rows(cursor: Any) -> list[dict[str, Any]]:
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _evidence_rows(cursor: Any) -> list[dict[str, Any]]:
        rows = []
        for row in cursor.fetchall():
            payload = dict(row)
            raw_sequence = payload.pop("tool_sequence_json", None)
            payload["tool_sequence"] = json.loads(raw_sequence) if raw_sequence else []
            rows.append(payload)
        return rows

    @staticmethod
    def _current_revision(conn: Any, topic_id: str) -> Any:
        return conn.execute(
            """
            SELECT *
            FROM topic_revisions
            WHERE topic_id = ?
            ORDER BY revision DESC
            LIMIT 1
            """,
            (topic_id,),
        ).fetchone()

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "repo"

    def _unique_slug(self, conn: Any, value: str) -> str:
        base = self._slugify(value)
        slug = base
        suffix = 2
        while conn.execute("SELECT 1 FROM projects WHERE slug = ?", (slug,)).fetchone():
            slug = f"{base}-{suffix}"
            suffix += 1
        return slug

    @staticmethod
    def _upsert_session(conn: Any, project_id: str, event: IngestionEvent) -> None:
        session_id = event.payload.get("session_id")
        if not session_id:
            return
        conn.execute(
            """
            INSERT INTO sessions (id, project_id, provider, source_path, started_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                provider = excluded.provider,
                source_path = excluded.source_path
            """,
            (str(session_id), project_id, event.provider, event.payload.get("source_path")),
        )

    def _seed_demo(self, conn: Any) -> None:
        conn.execute(
            "INSERT INTO projects (id, slug, name, repo_path, is_demo) VALUES (?, ?, ?, ?, 1)",
            (DEMO_PROJECT_ID, "docs-api", "Docs API", "/demo/docs-api"),
        )
        topics = [
            (
                "tenant-cache-isolation",
                "Tenant isolation in retrieval cache",
                "check_recommended",
                "Cached retrieval results must never cross tenant boundaries.",
                "Claude touched the retrieval path, the decision has no ADR, and it protects tenant isolation.",
                "persistence",
                5,
                1,
                1,  # checkable
                1,  # rank
            ),
            (
                "rerank-threshold",
                "Rerank cutoff threshold",
                "check_recommended",
                "Low-confidence documents are trimmed before synthesis.",
                "High blast radius and no comment explains the cutoff.",
                "ranking",
                3,
                1,
                0,
                2,
            ),
            (
                "source-window",
                "Source window ordering",
                "practiced",
                "The answer builder preserves source order before citation packing.",
                "Previously practiced, but still important to the answer path.",
                "retrieval",
                4,
                0,
                0,
                3,
            ),
            (
                "retry-budget",
                "Provider retry budget",
                "code_changed_since_practice",
                "The model client limits retries so failures stay observable.",
                "Code changed since the last practice event.",
                "external_api",
                2,
                0,
                0,
                4,
            ),
        ]
        conn.executemany(
            """
            INSERT INTO topics
            (id, project_id, provider, title, state, summary, why_now, risk_class, caller_count, claude_authored, checkable, rank)
            VALUES (?, 'project-docs-api', 'claude_code', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            topics,
        )
        conn.execute(
            "INSERT INTO commits (sha, project_id) VALUES ('demo-seed', 'project-docs-api')"
        )
        conn.execute(
            """
            INSERT INTO sessions (id, project_id, provider, source_path)
            VALUES (?, ?, ?, ?)
            """,
            (
                "claude-demo-session",
                "project-docs-api",
                "claude_code",
                "~/.claude/projects/demo.jsonl",
            ),
        )
        conn.execute(
            """
            INSERT INTO topic_revisions
            (id, topic_id, revision, commit_sha, code_path, invariant, risk_class, fingerprint)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tenant-cache-isolation-rev-1",
                "tenant-cache-isolation",
                1,
                "demo-seed",
                "retrieval/rerank.py",
                "Candidate documents must be filtered by tenant_id before ranking.",
                "persistence",
                "demo-tenant-cache-isolation-v1",
            ),
        )
        conn.executemany(
            """
            INSERT INTO evidence
            (topic_id, provider, session_id, source_path, tool_sequence_json, link_confidence, kind, title, body)
            VALUES (?, 'claude_code', ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "tenant-cache-isolation",
                    None,
                    None,
                    "[]",
                    "hand_verified",
                    "code",
                    "retrieval/rerank.py",
                    "visible_documents_for_tenant filters candidate documents by tenant_id before ranking.",
                ),
                (
                    "tenant-cache-isolation",
                    "claude-demo-session",
                    "~/.claude/projects/demo.jsonl",
                    json.dumps(
                        [
                            "Read retrieval/rerank.py",
                            "Edit retrieval/rerank.py",
                            "Bash python -m pytest",
                        ]
                    ),
                    "hand_verified",
                    "claude_receipt",
                    "Claude Code session",
                    "Read retrieval/rerank.py -> Edit retrieval/rerank.py -> Bash python -m pytest.",
                ),
            ],
        )
        evidence_rows = conn.execute(
            "SELECT id, kind FROM evidence WHERE topic_id = ?",
            ("tenant-cache-isolation",),
        ).fetchall()
        conn.executemany(
            """
            INSERT INTO revision_evidence (topic_revision_id, evidence_id, role, confidence)
            VALUES ('tenant-cache-isolation-rev-1', ?, ?, 'hand_verified')
            """,
            [(row["id"], row["kind"]) for row in evidence_rows],
        )
        conn.execute(
            """
            INSERT INTO check_recipes
            (id, topic_id, topic_revision_id, fixture_source, target_file, test_command, mutation_before, mutation_after)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "recipe-tenant-cache-isolation",
                "tenant-cache-isolation",
                "tenant-cache-isolation-rev-1",
                "@hero_repo",
                "retrieval/rerank.py",
                "python -m pytest tests",
                "return [doc for doc in documents if doc.tenant_id == tenant_id]",
                "return list(documents)",
            ),
        )
        conn.execute(
            """
            INSERT INTO topic_events (topic_id, topic_revision_id, event_type, body)
            VALUES (?, ?, 'created', ?)
            """,
            (
                "tenant-cache-isolation",
                "tenant-cache-isolation-rev-1",
                "Seeded demo topic revision.",
            ),
        )
        conn.commit()
