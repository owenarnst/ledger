from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Callable

from .analyst import (
    ANALYSIS_SCHEMA_VERSION,
    Analyst,
    AnalystIndex,
    DiscoveryResult,
    TraceLocator,
    create_analyst,
)
from .coach import DEFAULT_COACH_MODEL, Coach, create_coach
from .db import connect, initialize_schema
from .exercise_generation import CliExercisePlanGenerator, ExercisePlanGenerator, fallback_plan, normalize_difficulty
from .exercise_templates import public_plan, validate_answers
from .extraction import resolve_head_sha
from .ingestion import DEFAULT_PROVIDER, IngestionEvent, TraceSegment, adapter_for, claude_transcripts_dir
from .pseudocode import build_pseudocode_comments
from .sandbox import create_sandbox, run_pytest, sandbox_spec_for
from .verifier import VerificationResult, VerifiedTopic, verify_proposals


DEFAULT_DB_PATH = Path.home() / ".ledger" / "ledger.db"
DEFAULT_SANDBOX_ROOT = Path.home() / ".ledger" / "sandboxes"

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
_PROVIDER_LABEL = {"claude_code": "Claude"}


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
        exercise_generator: ExercisePlanGenerator | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.sandbox_root = Path(sandbox_root)
        self.coach = coach or create_coach()
        self.exercise_generator = exercise_generator or CliExercisePlanGenerator()

    def initialize(self) -> None:
        with connect(self.db_path) as conn:
            initialize_schema(conn)
            if conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
                self._seed(conn)
            else:
                self._ensure_seeded_revisions(conn)

    def initialize_schema(self) -> None:
        with connect(self.db_path) as conn:
            initialize_schema(conn)

    def seed_demo_data(self) -> None:
        with connect(self.db_path) as conn:
            self._seed(conn)

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

    def reconcile_head(self, cwd: str | Path, current_head: str | None) -> dict[str, Any]:
        """At SessionStart, capture the current HEAD if it differs from the last
        recorded one — catches pulls/rebases/commits whose post-commit hook never ran."""
        project = self.initialize_project_from_repo(cwd)
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT head_sha FROM hook_events "
                "WHERE project_id = ? AND head_sha IS NOT NULL "
                "ORDER BY rowid DESC LIMIT 1",
                (project["id"],),
            ).fetchone()
        last = row["head_sha"] if row else None
        if current_head and current_head != last:
            self.record_hook_event(
                provider="git",
                event_type="session-reconcile",
                cwd=cwd,
                head_sha=current_head,
                payload={"reconciled_from": last},
            )
            return {"reconciled": True, "from": last, "to": current_head}
        return {"reconciled": False, "head": current_head}

    def initialize_project_from_repo(
        self,
        repo_path: str | Path,
        *,
        name: str | None = None,
    ) -> dict[str, Any]:
        path = Path(repo_path).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise ValueError(f"repository path does not exist: {repo_path}")

        slug = self._slugify(name or path.name)
        project_id = f"project-{slug}"
        with connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT * FROM projects WHERE repo_path = ? OR slug = ?",
                (str(path), slug),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE projects SET name = ?, repo_path = ? WHERE id = ?",
                    (name or path.name, str(path), existing["id"]),
                )
                conn.commit()
                return dict(conn.execute("SELECT * FROM projects WHERE id = ?", (existing["id"],)).fetchone())

            conn.execute(
                "INSERT INTO projects (id, slug, name, repo_path) VALUES (?, ?, ?, ?)",
                (project_id, slug, name or path.name, str(path)),
            )
            conn.commit()
            return dict(conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())

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
        event = IngestionEvent(
            provider=provider,
            event_type=event_type,
            cwd=str(cwd),
            branch=branch,
            head_sha=head_sha,
            payload=payload or {},
        )
        project = self.initialize_project_from_repo(event.cwd)
        with connect(self.db_path) as conn:
            self._upsert_session(conn, project["id"], event)
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

        # Ingestion never mints Topics (ADR-0002): provenance only. The agentic
        # discovery pipeline (extract_or_refresh_topics) is the sole topic source.
        return {
            "project": project,
            "event": stored_event,
            "topics": self.list_topics(project["slug"]),
        }

    def import_provider_sessions(self, provider: str, root: str | Path) -> dict[str, Any]:
        adapter = adapter_for(provider)
        events = adapter.read_sessions(root)
        imported = []
        topics: list[dict[str, Any]] = []
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
            topics = result["topics"]
        return {"provider": provider, "imported": len(imported), "events": imported, "topics": topics}

    def _import_claude_transcripts(
        self, repo_root: Path, *, progress: Callable[[str], None] | None = None
    ) -> int:
        """Ingest the repo's real Claude Code transcripts as analyst recall material.

        Reads ``~/.claude/projects/<repo>/*.jsonl`` (the live sessions, not a fixture)
        into the sessions table so :meth:`_trace_locators` can offer their prompt +
        tool-call segments to the analyst. Returns the number of sessions imported; a
        no-op (0) when the repo has no transcripts on this machine.
        """
        transcripts = claude_transcripts_dir(repo_root)
        if not transcripts.exists():
            return 0
        imported = self.import_provider_sessions(DEFAULT_PROVIDER, transcripts)["imported"]
        if progress and imported:
            progress(f"Ingested {imported} real Claude Code session(s) from {transcripts}")
        return imported

    # ------------------------------------------------------------------ #
    # Topic discovery — agentic worklist (ADR-0002)
    # ------------------------------------------------------------------ #

    def extract_or_refresh_topics(
        self,
        repo_path: str | Path,
        *,
        analyst: Analyst | None = None,
        progress: Callable[[str], None] | None = None,
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

        # The Agent trace's recall material is the repo's real Claude Code sessions:
        # ingest ~/.claude transcripts so the analyst can cite the prompts + tool calls
        # that actually built this code. No-op when none exist (e.g. CI, a fresh clone).
        self._import_claude_transcripts(repo_root, progress=progress)

        index = AnalystIndex.from_repo(repo_root, traces=self._trace_locators(project))
        discovery = analyst.discover(repo_root, index, progress=progress)
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
            "fallback_reason": discovery.fallback_reason,
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
        """Development traces the analyst is allowed to cite (recall material).

        Each locator carries the session's addressable prompt/tool-call segments so
        the analyst can cite specific ones and the verifier can resolve them.
        """
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, provider, source_path, segments_json FROM sessions "
                "WHERE project_id = ? ORDER BY id",
                (project["id"],),
            ).fetchall()
        locators: list[TraceLocator] = []
        for r in rows:
            raw = json.loads(r["segments_json"] or "[]")
            segments = tuple(TraceSegment.from_dict(s) for s in raw if isinstance(s, dict))
            locators.append(
                TraceLocator(
                    provider=r["provider"],
                    session_id=r["id"],
                    source_path=r["source_path"],
                    segments=segments,
                )
            )
        return tuple(locators)

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
                 risk_class, caller_count, claude_authored, rank,
                 impact_level, impact_consequence, priority_rationale)
                VALUES (?, ?, 'claude_code', ?, 'check_recommended', ?, ?, ?, ?, 0, ?, ?, ?, ?)
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
            # Refresh display facts/rank; preserve lifecycle. A code change under
            # a practiced topic re-surfaces it.
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
            tool_sequence = [
                f"{s.tool} {s.target}".strip()
                for s in trace.segments
                if s.kind == "tool_call"
            ]
            segments_json = json.dumps([s.as_dict() for s in trace.segments])
            body = self._render_trace_body(trace.segments, trace.relevance)
            trace_eid = conn.execute(
                """
                INSERT INTO evidence
                (topic_id, provider, session_id, source_path, tool_sequence_json, segments_json,
                 link_confidence, kind, title, body, excerpt_sha, relevance)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'trace', ?, ?, NULL, ?)
                """,
                (topic_id, trace.provider, trace.session_id, trace.source_path,
                 json.dumps(tool_sequence), segments_json,
                 trace.link_confidence, f"{trace.provider} session", body, trace.relevance),
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
                    SELECT provider, session_id, source_path, tool_sequence_json, segments_json,
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

    def get_session(self, session_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not session:
                raise KeyError(session_id)
            return dict(session)

    def create_check(self, topic_id: str, difficulty: str | None = None) -> dict[str, Any]:
        check_id = uuid.uuid4().hex
        selected_difficulty = normalize_difficulty(difficulty)
        sandbox_path = self.sandbox_root / check_id
        # The sandbox exercise is chosen by topic: each topic injects the canonical
        # violation of its own invariant into its own target file (sandbox_spec_for).
        spec = sandbox_spec_for(topic_id)
        with connect(self.db_path) as conn:
            revision = self._current_revision(conn, topic_id)
            if not revision:
                raise KeyError(topic_id)
            create_sandbox(sandbox_path, spec)
            template = self._exercise_plan_for_check(conn, topic_id, dict(revision), selected_difficulty)
            conn.execute(
                """
                INSERT INTO checks
                (id, topic_id, topic_revision_id, state, sandbox_path, target_file, test_command, difficulty, template_id, plan_json)
                VALUES (?, ?, ?, 'in_progress', ?, ?, 'python -m pytest -s tests', ?, ?, ?)
                """,
                (
                    check_id,
                    topic_id,
                    revision["id"],
                    str(sandbox_path),
                    spec.target_file,
                    template["difficulty"],
                    template["template_id"],
                    json.dumps(template, sort_keys=True),
                ),
            )
            conn.execute("UPDATE topics SET state = 'in_progress' WHERE id = ?", (topic_id,))
            conn.execute(
                """
                INSERT INTO topic_events (topic_id, topic_revision_id, event_type, body)
                VALUES (?, ?, 'check_started', ?)
                """,
                (topic_id, revision["id"], check_id),
            )
            conn.commit()
        return self.get_check(check_id)

    def _exercise_plan_for_check(self, conn: Any, topic_id: str, revision: dict[str, Any], difficulty: str) -> dict[str, Any]:
        cached = conn.execute(
            """
            SELECT plan_json
            FROM exercise_plans
            WHERE topic_revision_id = ? AND difficulty = ?
            """,
            (revision["id"], difficulty),
        ).fetchone()
        if cached:
            return json.loads(cached["plan_json"])

        topic = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
        if not topic:
            raise KeyError(topic_id)
        try:
            plan = self.exercise_generator.generate_plan(topic=dict(topic), revision=revision, difficulty=difficulty)
        except Exception:
            plan = fallback_plan(difficulty)
        conn.execute(
            """
            INSERT INTO exercise_plans (id, topic_id, topic_revision_id, difficulty, provider, plan_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                topic_id,
                revision["id"],
                difficulty,
                getattr(self.exercise_generator, "provider", "fallback"),
                json.dumps(plan, sort_keys=True),
            ),
        )
        return plan

    def get_check(self, check_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            check = conn.execute("SELECT * FROM checks WHERE id = ?", (check_id,)).fetchone()
            if not check:
                raise KeyError(check_id)
            payload = dict(check)
            plan = json.loads(payload.get("plan_json") or "{}")
            payload["plan"] = public_plan(plan)
            payload.pop("plan_json", None)
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

    def run_check(self, check_id: str) -> dict[str, Any]:
        check = self.get_check(check_id)
        try:
            result = run_pytest(Path(check["sandbox_path"]))
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

    def ask_coach(self, check_id: str, question: str, model: str | None = None) -> dict[str, str]:
        check = self.get_check(check_id)
        topic = self.get_topic(check["topic_id"])
        latest = self._latest_attempt_output(check_id)
        coach = create_coach(model) if model else self.coach
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
        return {
            "question": question,
            "model": getattr(coach, "model_id", DEFAULT_COACH_MODEL),
            "response": response,
        }

    def pseudocode_comments(self, check_id: str, relative_path: str) -> dict[str, Any]:
        check = self.get_check(check_id)
        topic = self.get_topic(check["topic_id"])
        current = self.read_check_file(check_id, relative_path)["content"]
        reference_path = Path(__file__).resolve().parent / "fixtures" / "hero_repo" / relative_path
        if not reference_path.exists():
            raise FileNotFoundError(relative_path)
        return build_pseudocode_comments(
            file_path=relative_path,
            current_code=current,
            reference_code=reference_path.read_text(),
            invariant=(topic.get("current_revision") or {}).get("invariant"),
        )

    def submit_check_answers(self, check_id: str, answers: dict[str, int]) -> dict[str, Any]:
        check = self.get_check(check_id)
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT plan_json FROM checks WHERE id = ?", (check_id,)).fetchone()
            if not row:
                raise KeyError(check_id)
            result = validate_answers(json.loads(row["plan_json"]), answers)
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

    def _latest_attempt_output(self, check_id: str) -> str:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT output FROM attempts WHERE check_id = ? ORDER BY id DESC LIMIT 1",
                (check_id,),
            ).fetchone()
            return row["output"] if row else "No check has been run yet."

    def _candidate_topic_files(self, repo_path: Path, payload: dict[str, Any]) -> list[str]:
        changed_files = payload.get("changed_files") or payload.get("files") or []
        candidates = [
            str(path)
            for path in changed_files
            if isinstance(path, str) and not path.endswith("/") and (repo_path / path).is_file()
        ]
        if candidates:
            return candidates[:5]

        discovered = []
        for pattern in ("**/*.py", "**/*.js", "**/*.ts", "**/*.tsx", "**/*.jsx"):
            discovered.extend(repo_path.glob(pattern))
        return [
            str(path.relative_to(repo_path))
            for path in discovered
            if ".git" not in path.parts and "node_modules" not in path.parts
        ][:5]

    def _summarize_file(self, path: Path) -> str:
        if not path.exists():
            return "File was referenced by a hook event but is no longer present."
        lines = path.read_text(errors="replace").splitlines()
        first_meaningful = next((line.strip() for line in lines if line.strip()), "")
        if first_meaningful:
            return f"{path.name} exists in the tracked repository. First meaningful line: {first_meaningful[:160]}"
        return f"{path.name} exists in the tracked repository."

    def _hook_why_now(self, event: Any) -> str:
        details = [f"{event['event_type']} captured repository activity"]
        if event["branch"]:
            details.append(f"on branch {event['branch']}")
        if event["head_sha"]:
            details.append(f"at {event['head_sha'][:12]}")
        return " ".join(details) + "."

    def _hook_event_title(self, event: Any) -> str:
        if event["branch"]:
            return f"{event['event_type']} on {event['branch']}"
        return event["event_type"]

    def _hook_event_body(self, event: Any) -> str:
        payload = json.loads(event["payload_json"])
        changed = payload.get("changed_files") or payload.get("files") or []
        changed_text = ", ".join(changed) if changed else "no changed files reported"
        head = event["head_sha"] or "unknown HEAD"
        return f"Hook captured {changed_text} at {head}."

    def _check_file_path(self, check_id: str, relative_path: str) -> Path:
        check = self.get_check(check_id)
        root = Path(check["sandbox_path"]).resolve()
        path = (root / relative_path).resolve()
        if root not in path.parents and path != root:
            raise ValueError("path escapes sandbox")
        if not path.exists():
            raise FileNotFoundError(relative_path)
        return path

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
            raw_segments = payload.pop("segments_json", None)
            payload["segments"] = json.loads(raw_segments) if raw_segments else []
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

    @staticmethod
    def _receipt_kind(provider: str) -> str:
        if provider == DEFAULT_PROVIDER:
            return "claude_receipt"
        return f"{provider}_receipt"

    @staticmethod
    def _render_trace_body(segments: Any, fallback: str) -> str:
        """A plain-text rendering of the agent-trace hunk for the body column and
        any non-segment-aware consumer; the UI renders the structured segments."""
        lines: list[str] = []
        for s in segments:
            if s.kind == "prompt":
                lines.append(f'"{s.text}"')
            else:
                lines.append(f"{s.tool} {s.target}".strip())
        return "\n".join(lines) or fallback

    @staticmethod
    def _tool_sequence_json(payload: dict[str, Any]) -> str:
        sequence = payload.get("tool_sequence") or []
        if not isinstance(sequence, list):
            sequence = []
        return json.dumps([str(item) for item in sequence], sort_keys=True)

    @staticmethod
    def _upsert_session(conn: Any, project_id: str, event: IngestionEvent) -> None:
        session_id = event.payload.get("session_id")
        if not session_id:
            return
        segments_json = json.dumps(event.payload.get("segments") or [])
        # Preserve a previously-ingested segment list when a later bare hook event
        # for the same session carries none (an empty '[]' never clobbers a hunk).
        conn.execute(
            """
            INSERT INTO sessions (id, project_id, provider, source_path, segments_json, started_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                provider = excluded.provider,
                source_path = excluded.source_path,
                segments_json = CASE
                    WHEN excluded.segments_json = '[]' THEN sessions.segments_json
                    ELSE excluded.segments_json
                END
            """,
            (
                str(session_id),
                project_id,
                event.provider,
                event.payload.get("source_path"),
                segments_json,
            ),
        )

    def _seed(self, conn: Any) -> None:
        """Seed the demo worklist from a captured live Topic Analyst run.

        The topics, invariants, impact, and code-anchor evidence in
        ``fixtures/demo_seed.json`` were produced by the agentic analyst
        (claude-opus-4-8) over docs-search-api and captured verbatim -- not
        hand-authored. Seeding replays that real discovery deterministically.
        The tenant-isolation topic keeps the canonical ``tenant-cache-isolation``
        id so the Debug-to-Own check stays attached to it.
        """
        seed = json.loads(
            (Path(__file__).parent / "fixtures" / "demo_seed.json").read_text()
        )
        conn.execute(
            "INSERT INTO projects (id, slug, name, repo_path) VALUES (?, ?, ?, ?)",
            (
                "project-docs-search-api",
                "docs-search-api",
                "Docs Search API",
                str(Path.home() / "Projects" / "docs-search-api"),
            ),
        )
        conn.execute(
            "INSERT INTO commits (sha, project_id) VALUES (?, 'project-docs-search-api')",
            (seed["commit_sha"],),
        )
        for topic in seed["topics"]:
            conn.execute(
                """
                INSERT INTO topics
                (id, project_id, provider, title, state, summary, why_now, risk_class,
                 caller_count, claude_authored, rank, impact_level, impact_consequence,
                 priority_rationale)
                VALUES (?, 'project-docs-search-api', 'claude_code', ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?)
                """,
                (
                    topic["id"], topic["title"], topic["state"], topic["summary"],
                    topic["why_now"], topic["risk_class"], topic["caller_count"],
                    topic["claude_authored"], topic["rank"], topic["impact_level"],
                    topic["impact_consequence"], topic["priority_rationale"],
                ),
            )
            rev = topic["revision"]
            conn.execute(
                """
                INSERT INTO topic_revisions
                (id, topic_id, revision, commit_sha, code_path, invariant, risk_class, fingerprint)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rev["id"], topic["id"], rev["revision"], rev["commit_sha"],
                    rev["code_path"], rev["invariant"], rev["risk_class"], rev["fingerprint"],
                ),
            )
            for ev in topic["evidence"]:
                evidence_id = conn.execute(
                    """
                    INSERT INTO evidence
                    (topic_id, provider, session_id, source_path, tool_sequence_json, segments_json,
                     link_confidence, kind, title, body, excerpt_sha, relevance)
                    VALUES (?, 'claude_code', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        topic["id"], ev["session_id"], ev["source_path"],
                        json.dumps(ev.get("tool_sequence") or []),
                        json.dumps(ev.get("segments") or []), ev["link_confidence"],
                        ev["kind"], ev["title"], ev["body"], ev["excerpt_sha"], ev["relevance"],
                    ),
                ).lastrowid
                conn.execute(
                    """
                    INSERT INTO revision_evidence (topic_revision_id, evidence_id, role, confidence)
                    VALUES (?, ?, ?, ?)
                    """,
                    (rev["id"], evidence_id, ev["kind"], ev["link_confidence"]),
                )
            conn.execute(
                """
                INSERT INTO topic_events (topic_id, topic_revision_id, event_type, body)
                VALUES (?, ?, 'created', 'Seeded from the demo Topic Analyst run.')
                """,
                (topic["id"], rev["id"]),
            )
        # Pre-cache the hero check's exercise plans (live ClaudeAnalyst-generated,
        # captured in the fixture) so the Debug-to-Own MCQs load instantly and
        # deterministically instead of paying a live ``claude -p`` round-trip on the
        # first open of each difficulty. _exercise_plan_for_check reads this cache by
        # (topic_revision_id, difficulty); hard is sandbox-only and needs no plan.
        for entry in seed.get("exercise_plans", []):
            conn.execute(
                """
                INSERT INTO exercise_plans (id, topic_id, topic_revision_id, difficulty, provider, plan_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    entry["topic_id"],
                    entry["topic_revision_id"],
                    entry["difficulty"],
                    entry.get("provider", "claude"),
                    json.dumps(entry["plan"], sort_keys=True),
                ),
            )
        conn.commit()

    def _ensure_seeded_revisions(self, conn: Any) -> None:
        topic = conn.execute(
            "SELECT id FROM topics WHERE id = ?",
            ("tenant-cache-isolation",),
        ).fetchone()
        if not topic:
            return

        revision = conn.execute(
            "SELECT id FROM topic_revisions WHERE id = ?",
            ("tenant-cache-isolation-rev-1",),
        ).fetchone()
        if revision:
            return

        conn.execute(
            """
            INSERT OR IGNORE INTO commits (sha, project_id)
            VALUES ('demo-seed', 'project-docs-search-api')
            """
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
            INSERT INTO topic_events (topic_id, topic_revision_id, event_type, body)
            VALUES (?, ?, 'created', ?)
            """,
            (
                "tenant-cache-isolation",
                "tenant-cache-isolation-rev-1",
                "Backfilled demo topic revision.",
            ),
        )
        conn.commit()
