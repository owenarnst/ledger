from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from .coach import Coach, create_coach
from .db import connect, initialize_schema
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

    def initialize_schema(self) -> None:
        with connect(self.db_path) as conn:
            initialize_schema(conn)

    def seed_demo_data(self) -> None:
        with connect(self.db_path) as conn:
            self._seed(conn)

    def list_projects(self) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            return self._rows(conn.execute("SELECT * FROM projects ORDER BY created_at"))

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
    ) -> dict[str, Any]:
        project = self.initialize_project_from_repo(cwd)
        payload = payload or {}
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO hook_events (project_id, event_type, branch, head_sha, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project["id"], event_type, branch, head_sha, json.dumps(payload, sort_keys=True)),
            )
            conn.commit()
            event = dict(
                conn.execute("SELECT * FROM hook_events WHERE id = ?", (cursor.lastrowid,)).fetchone()
            )

        topics = self.extract_or_refresh_topics(project["id"])
        return {"project": project, "event": event, "topics": topics}

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
            for rank, relative_path in enumerate(candidate_files, start=1):
                topic_id = f"{project_id}-{self._slugify(relative_path)}"
                title = f"Understand {relative_path}"
                summary = f"{relative_path} changed in repository activity captured by Ledger."
                why_now = self._hook_why_now(latest_event)
                conn.execute(
                    """
                    INSERT INTO topics
                    (id, project_id, title, state, summary, why_now, risk_class, caller_count, claude_authored, rank)
                    VALUES (?, ?, ?, 'check_recommended', ?, ?, 'repo_activity', 1, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        state = excluded.state,
                        summary = excluded.summary,
                        why_now = excluded.why_now,
                        claude_authored = excluded.claude_authored,
                        rank = excluded.rank
                    """,
                    (
                        topic_id,
                        project_id,
                        title,
                        summary,
                        why_now,
                        int(latest_event["event_type"].lower() == "sessionstart"),
                        rank,
                    ),
                )
                conn.execute("DELETE FROM evidence WHERE topic_id = ?", (topic_id,))
                conn.executemany(
                    "INSERT INTO evidence (topic_id, kind, title, body) VALUES (?, ?, ?, ?)",
                    [
                        (
                            topic_id,
                            "code",
                            relative_path,
                            self._summarize_file(Path(project["repo_path"]) / relative_path),
                        ),
                        (
                            topic_id,
                            "hook_event",
                            self._hook_event_title(latest_event),
                            self._hook_event_body(latest_event),
                        ),
                    ],
                )
            conn.commit()
            return self.list_topics(project["slug"])

    def get_topic(self, topic_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            topic = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
            if not topic:
                raise KeyError(topic_id)
            payload = dict(topic)
            payload["evidence"] = self._rows(
                conn.execute("SELECT kind, title, body FROM evidence WHERE topic_id = ?", (topic_id,))
            )
            return payload

    def create_check(self, topic_id: str) -> dict[str, Any]:
        check_id = uuid.uuid4().hex
        sandbox_path = self.sandbox_root / check_id
        create_hero_sandbox(sandbox_path)
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO checks (id, topic_id, state, sandbox_path, target_file, test_command)
                VALUES (?, ?, 'in_progress', ?, 'retrieval/rerank.py', 'python -m pytest tests')
                """,
                (check_id, topic_id, str(sandbox_path)),
            )
            conn.execute("UPDATE topics SET state = 'in_progress' WHERE id = ?", (topic_id,))
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
        result = run_pytest(Path(check["sandbox_path"]))
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO attempts (check_id, passed, output, elapsed_ms) VALUES (?, ?, ?, ?)",
                (check_id, int(result.passed), result.output, result.elapsed_ms),
            )
            conn.commit()
        return {
            "check_id": check_id,
            "passed": result.passed,
            "output": result.output,
            "elapsed_ms": result.elapsed_ms,
        }

    def complete_check(self, check_id: str) -> dict[str, Any]:
        check = self.get_check(check_id)
        with connect(self.db_path) as conn:
            conn.execute(
                "UPDATE checks SET state = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (check_id,),
            )
            conn.execute("UPDATE topics SET state = 'practiced' WHERE id = ?", (check["topic_id"],))
            conn.commit()
        return self.get_check(check_id)

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
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "repo"

    def _seed(self, conn: Any) -> None:
        conn.execute(
            "INSERT INTO projects (id, slug, name, repo_path) VALUES (?, ?, ?, ?)",
            ("project-docs-api", "docs-api", "Docs API", "/demo/docs-api"),
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
            (id, project_id, title, state, summary, why_now, risk_class, caller_count, claude_authored, rank)
            VALUES (?, 'project-docs-api', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            topics,
        )
        conn.executemany(
            "INSERT INTO evidence (topic_id, kind, title, body) VALUES (?, ?, ?, ?)",
            [
                (
                    "tenant-cache-isolation",
                    "code",
                    "retrieval/rerank.py",
                    "visible_documents_for_tenant filters candidate documents by tenant_id before ranking.",
                ),
                (
                    "tenant-cache-isolation",
                    "claude_receipt",
                    "Claude Code session",
                    "Read retrieval/rerank.py -> Edit retrieval/rerank.py -> Bash python -m pytest.",
                ),
                (
                    "tenant-cache-isolation",
                    "missing_reasoning",
                    "Trail scan",
                    "Searched ADRs, CONTEXT, README, comments, and commit messages; no tenant cache rationale found.",
                ),
            ],
        )
        conn.commit()
