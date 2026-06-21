from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from .coach import Coach, create_coach
from .db import connect, initialize_schema
from .ingestion import DEFAULT_PROVIDER, IngestionEvent, adapter_for
from .sandbox import create_hero_sandbox, run_pytest


DEFAULT_DB_PATH = Path.home() / ".ledger" / "ledger.db"
DEFAULT_SANDBOX_ROOT = Path.home() / ".ledger" / "sandboxes"


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
            return self._rows(conn.execute("SELECT * FROM topics ORDER BY rank"))

    def list_topics(self, project_slug: str) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            return self._rows(
                conn.execute(
                    """
                    SELECT topics.*
                    FROM topics
                    JOIN projects ON projects.id = topics.project_id
                    WHERE projects.slug = ?
                    ORDER BY topics.rank
                    """,
                    (project_slug,),
                )
            )

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

        topics = self.extract_or_refresh_topics(project["id"])
        return {"project": project, "event": stored_event, "topics": topics}

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

    def extract_or_refresh_topics(self, project_id: str) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not project:
                raise KeyError(project_id)
            latest_event = conn.execute(
                """
                SELECT * FROM hook_events
                WHERE project_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            if not latest_event:
                return self.list_topics(project["slug"])

            payload = json.loads(latest_event["payload_json"])
            candidate_files = self._candidate_topic_files(Path(project["repo_path"]), payload)
            if latest_event["head_sha"]:
                conn.execute(
                    """
                    INSERT INTO commits (sha, project_id)
                    VALUES (?, ?)
                    ON CONFLICT(sha) DO NOTHING
                    """,
                    (latest_event["head_sha"], project_id),
                )
            for rank, relative_path in enumerate(candidate_files, start=1):
                topic_id = f"{project_id}-{self._slugify(relative_path)}"
                revision_id = f"{topic_id}-rev-1"
                title = f"Understand {relative_path}"
                summary = f"{relative_path} changed in repository activity captured by Ledger."
                why_now = self._hook_why_now(latest_event)
                conn.execute(
                    """
                    INSERT INTO topics
                    (id, project_id, provider, title, state, summary, why_now, risk_class, caller_count, claude_authored, rank)
                    VALUES (?, ?, ?, ?, 'check_recommended', ?, ?, 'repo_activity', 1, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        provider = excluded.provider,
                        state = excluded.state,
                        summary = excluded.summary,
                        why_now = excluded.why_now,
                        claude_authored = excluded.claude_authored,
                        rank = excluded.rank
                    """,
                    (
                        topic_id,
                        project_id,
                        latest_event["provider"],
                        title,
                        summary,
                        why_now,
                        int(latest_event["event_type"].lower() == "sessionstart"),
                        rank,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO topic_revisions
                    (id, topic_id, revision, commit_sha, code_path, invariant, risk_class, fingerprint)
                    VALUES (?, ?, 1, ?, ?, ?, 'repo_activity', ?)
                    ON CONFLICT(id) DO UPDATE SET
                        commit_sha = excluded.commit_sha,
                        code_path = excluded.code_path,
                        invariant = excluded.invariant,
                        risk_class = excluded.risk_class,
                        fingerprint = excluded.fingerprint
                    """,
                    (
                        revision_id,
                        topic_id,
                        latest_event["head_sha"],
                        relative_path,
                        f"Understand and safely maintain {relative_path}.",
                        f"{topic_id}:{latest_event['head_sha'] or 'unknown'}",
                    ),
                )
                conn.execute("DELETE FROM evidence WHERE topic_id = ?", (topic_id,))
                conn.executemany(
                    """
                    INSERT INTO evidence
                    (topic_id, provider, session_id, source_path, tool_sequence_json, link_confidence, kind, title, body)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            topic_id,
                            latest_event["provider"],
                            None,
                            None,
                            "[]",
                            "heuristic",
                            "code",
                            relative_path,
                            self._summarize_file(Path(project["repo_path"]) / relative_path),
                        ),
                        (
                            topic_id,
                            latest_event["provider"],
                            payload.get("session_id"),
                            payload.get("source_path"),
                            self._tool_sequence_json(payload),
                            payload.get("link_confidence") or "heuristic",
                            self._receipt_kind(latest_event["provider"]),
                            self._hook_event_title(latest_event),
                            self._hook_event_body(latest_event),
                        ),
                        (
                            topic_id,
                            latest_event["provider"],
                            None,
                            None,
                            "[]",
                            "heuristic",
                            "hook_event",
                            self._hook_event_title(latest_event),
                            self._hook_event_body(latest_event),
                        ),
                    ],
                )
                conn.execute("DELETE FROM revision_evidence WHERE topic_revision_id = ?", (revision_id,))
                evidence_rows = conn.execute(
                    "SELECT id, kind FROM evidence WHERE topic_id = ?",
                    (topic_id,),
                ).fetchall()
                conn.executemany(
                    """
                    INSERT INTO revision_evidence (topic_revision_id, evidence_id, role, confidence)
                    VALUES (?, ?, ?, 'heuristic')
                    """,
                    [(revision_id, row["id"], row["kind"]) for row in evidence_rows],
                )
                conn.execute(
                    """
                    INSERT INTO topic_events (topic_id, topic_revision_id, event_type, body)
                    VALUES (?, ?, 'refreshed', ?)
                    """,
                    (topic_id, revision_id, self._hook_event_body(latest_event)),
                )
            conn.commit()
            return self.list_topics(project["slug"])

    def get_topic(self, topic_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            topic = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
            if not topic:
                raise KeyError(topic_id)
            payload = dict(topic)
            revision = self._current_revision(conn, topic_id)
            payload["current_revision"] = dict(revision) if revision else None
            payload["evidence"] = self._evidence_rows(
                conn.execute(
                    """
                    SELECT provider, session_id, source_path, tool_sequence_json, link_confidence, kind, title, body
                    FROM evidence
                    WHERE topic_id = ?
                    """,
                    (topic_id,),
                )
            )
            return payload

    def get_session(self, session_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not session:
                raise KeyError(session_id)
            return dict(session)

    def create_check(self, topic_id: str) -> dict[str, Any]:
        check_id = uuid.uuid4().hex
        sandbox_path = self.sandbox_root / check_id
        create_hero_sandbox(sandbox_path)
        with connect(self.db_path) as conn:
            revision = self._current_revision(conn, topic_id)
            if not revision:
                raise KeyError(topic_id)
            conn.execute(
                """
                INSERT INTO checks (id, topic_id, topic_revision_id, state, sandbox_path, target_file, test_command)
                VALUES (?, ?, ?, 'in_progress', ?, 'retrieval/rerank.py', 'python -m pytest tests')
                """,
                (check_id, topic_id, revision["id"], str(sandbox_path)),
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

    def _seed(self, conn: Any) -> None:
        conn.execute(
            "INSERT INTO projects (id, slug, name, repo_path) VALUES (?, ?, ?, ?)",
            ("project-docs-search-api", "docs-search-api", "Docs Search API", str(Path.home() / "Projects" / "docs-search-api")),
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
                1,
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
                4,
            ),
        ]
        conn.executemany(
            """
            INSERT INTO topics
            (id, project_id, provider, title, state, summary, why_now, risk_class, caller_count, claude_authored, rank)
            VALUES (?, 'project-docs-search-api', 'claude_code', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            topics,
        )
        conn.execute(
            """
            INSERT INTO commits (sha, project_id)
            VALUES ('demo-seed', 'project-docs-search-api')
            """
        )
        conn.execute(
            """
            INSERT INTO sessions (id, project_id, provider, source_path)
            VALUES (?, ?, ?, ?)
            """,
            (
                "claude-demo-session",
                "project-docs-search-api",
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
                (
                    "tenant-cache-isolation",
                    None,
                    None,
                    "[]",
                    "hand_verified",
                    "missing_reasoning",
                    "Trail scan",
                    "Searched ADRs, CONTEXT, README, comments, and commit messages; no tenant cache rationale found.",
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

    def _ensure_seeded_revisions(self, conn: Any) -> None:
        topic = conn.execute(
            "SELECT id FROM topics WHERE id = ?",
            ("tenant-cache-isolation",),
        ).fetchone()
        if not topic:
            return

        conn.execute(
            """
            INSERT OR IGNORE INTO sessions (id, project_id, provider, source_path)
            VALUES (?, ?, ?, ?)
            """,
            (
                "claude-demo-session",
                "project-docs-search-api",
                "claude_code",
                "~/.claude/projects/demo.jsonl",
            ),
        )
        receipt = conn.execute(
            """
            SELECT id FROM evidence
            WHERE topic_id = ? AND kind = 'claude_receipt'
            """,
            ("tenant-cache-isolation",),
        ).fetchone()
        if receipt:
            conn.execute(
                """
                UPDATE evidence
                SET
                    provider = 'claude_code',
                    session_id = ?,
                    source_path = ?,
                    tool_sequence_json = ?,
                    link_confidence = 'hand_verified'
                WHERE id = ?
                """,
                (
                    "claude-demo-session",
                    "~/.claude/projects/demo.jsonl",
                    json.dumps(
                        [
                            "Read retrieval/rerank.py",
                            "Edit retrieval/rerank.py",
                            "Bash python -m pytest",
                        ]
                    ),
                    receipt["id"],
                ),
            )

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
