from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from .repository import DEFAULT_DB_PATH, DEFAULT_SANDBOX_ROOT, LedgerRepository


DEFAULT_SPOOL_DIR = Path.home() / ".ledger" / "spool"


class HookSpool:
    def __init__(self, spool_dir: str | Path = DEFAULT_SPOOL_DIR) -> None:
        self.spool_dir = Path(spool_dir)

    def write(self, event: dict[str, Any]) -> Path:
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        path = self.spool_dir / f"{time.time_ns()}.json"
        path.write_text(json.dumps(event, sort_keys=True) + "\n")
        return path

    def drain(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.spool_dir.glob("*.json")):
            try:
                events.append(json.loads(path.read_text()))
            finally:
                path.unlink(missing_ok=True)
        return events

    def pending_count(self) -> int:
        if not self.spool_dir.exists():
            return 0
        return len(list(self.spool_dir.glob("*.json")))


def build_session_start_nudge(
    repo: LedgerRepository,
    *,
    cwd: str | Path,
    base_url: str = "http://127.0.0.1:4317",
) -> str:
    project = repo.initialize_project_from_repo(cwd)
    topics = repo.list_topics(project["slug"])
    ready_states = {"check_recommended", "code_changed_since_practice"}
    # A check is only "ready" when the Topic both wants one and has a curated
    # recipe to run; file activity alone never counts.
    ready = sum(
        1 for topic in topics if topic["state"] in ready_states and topic.get("checkable")
    )
    return f"Ledger: {ready} checks ready for {project['slug']} · Open {base_url}/p/{project['slug']}"


def drain_spool(
    repo: LedgerRepository,
    *,
    spool_dir: str | Path = DEFAULT_SPOOL_DIR,
) -> dict[str, Any]:
    spool = HookSpool(spool_dir)
    imported = []
    for event in spool.drain():
        imported.append(
            repo.record_hook_event(
                provider=event.get("provider", "git"),
                event_type=event.get("event_type", "post-commit"),
                cwd=event["cwd"],
                branch=event.get("branch"),
                head_sha=event.get("head_sha"),
                payload=event.get("payload") or {"changed_files": event.get("changed_files", [])},
            )
        )
    return {"imported": len(imported), "events": imported}


def reset_ledger(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    sandbox_root: str | Path = DEFAULT_SANDBOX_ROOT,
    spool_dir: str | Path = DEFAULT_SPOOL_DIR,
) -> dict[str, Any]:
    db = Path(db_path)
    if db.exists():
        db.unlink()
    sandbox = Path(sandbox_root)
    if sandbox.exists():
        shutil.rmtree(sandbox)
    spool = Path(spool_dir)
    if spool.exists():
        shutil.rmtree(spool)
    repo = LedgerRepository(db_path=db, sandbox_root=sandbox)
    repo.initialize()
    return {
        "db_path": str(db),
        "sandbox_root": str(sandbox),
        "spool_dir": str(spool),
        "projects": repo.list_projects(),
    }
