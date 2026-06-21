from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .repository import DEFAULT_DB_PATH, DEFAULT_SANDBOX_ROOT, LedgerRepository


DEFAULT_SPOOL_DIR = Path.home() / ".ledger" / "spool"
DEFAULT_BASE_URL = "http://127.0.0.1:4317"


def _git(cwd: str | Path, *args: str) -> str | None:
    """Run a read-only git command; return stripped stdout or None on any failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


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
    base_url: str = DEFAULT_BASE_URL,
) -> str:
    line, _ = _nudge_details(repo, cwd=cwd, base_url=base_url)
    return line


def _nudge_details(
    repo: LedgerRepository,
    *,
    cwd: str | Path,
    base_url: str = DEFAULT_BASE_URL,
) -> tuple[str, int]:
    project = repo.initialize_project_from_repo(cwd)
    topics = repo.list_topics(project["slug"])
    ready_states = {"check_recommended", "code_changed_since_practice"}
    ready = sum(1 for topic in topics if topic["state"] in ready_states)
    line = (
        f"Ledger: {ready} checks ready for {project['slug']}. "
        "If Claude just helped with a complex change, this is a good moment to test your understanding. "
        f"Open {base_url}/p/{project['slug']}"
    )
    return line, ready


def spool_commit(cwd: str | Path, *, spool_dir: str | Path = DEFAULT_SPOOL_DIR) -> Path:
    """Called by the git post-commit hook. Gathers commit metadata and queues a
    spool event. Best-effort and fast; never raises into the caller's git flow."""
    root = _git(cwd, "rev-parse", "--show-toplevel") or str(Path(cwd).expanduser().resolve())
    changed = _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", "HEAD") or ""
    event = {
        "provider": "git",
        "event_type": "post-commit",
        "cwd": root,
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "head_sha": _git(root, "rev-parse", "HEAD"),
        "changed_files": [line for line in changed.splitlines() if line],
    }
    return HookSpool(spool_dir).write(event)


def session_start(
    repo: LedgerRepository,
    *,
    cwd: str | Path,
    base_url: str = DEFAULT_BASE_URL,
    spool_dir: str | Path = DEFAULT_SPOOL_DIR,
) -> dict[str, Any]:
    """Called by the Claude SessionStart hook. Imports queued commits, reconciles
    HEAD, and returns the nudge + the hookSpecificOutput envelope Claude Code expects."""
    drained = drain_spool(repo, spool_dir=spool_dir)
    reconciled = repo.reconcile_head(cwd, _git(cwd, "rev-parse", "HEAD"))
    line, ready = _nudge_details(repo, cwd=cwd, base_url=base_url)
    envelope = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                f"[Ledger] {line}. This is a session-start notification — "
                f"surface it to the user verbatim at the start of your first reply."
            ),
            "sessionTitle": f"Ledger: {ready} checks ready",
        }
    }
    return {"line": line, "ready": ready, "drained": drained["imported"], "reconciled": reconciled, "envelope": envelope}


def session_end(
    repo: LedgerRepository,
    *,
    cwd: str | Path,
    base_url: str = DEFAULT_BASE_URL,
    spool_dir: str | Path = DEFAULT_SPOOL_DIR,
) -> dict[str, Any]:
    """Called by the Claude SessionEnd hook. Imports queued commits and gives
    Claude conditional guidance; Claude decides whether the session warrants a reminder."""
    drained = drain_spool(repo, spool_dir=spool_dir)
    line, ready = _nudge_details(repo, cwd=cwd, base_url=base_url)
    envelope = {
        "hookSpecificOutput": {
            "hookEventName": "SessionEnd",
            "additionalContext": (
                f"[Ledger] {drained['imported']} recent commit event(s) were captured. "
                "Decide from the actual session content whether the work was complex, load-bearing, "
                "or Claude-assisted enough that the user should verify they understand it. "
                "If this was routine or cosmetic, say nothing about Ledger. "
                "If it is worth surfacing, write a short, friendly note in your own voice: "
                "name what changed, why it may be load-bearing, and invite the user to open Ledger. "
                f"Use this destination: {line}"
            ),
            "sessionTitle": f"Ledger: {ready} checks ready",
        }
    }
    return {"line": line, "ready": ready, "drained": drained["imported"], "envelope": envelope}


def install_hooks(
    repo_path: str | Path,
    *,
    interpreter: str,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Write the git post-commit hook and merge the Claude SessionStart hook into
    the target repo's .claude/settings.json. Idempotent; ensures ~/.ledger exists."""
    root = Path(repo_path).expanduser().resolve()
    if not (root / ".git").is_dir():
        raise ValueError(f"not a git repository (no .git dir): {root}")
    Path(DEFAULT_SPOOL_DIR).mkdir(parents=True, exist_ok=True)

    hooks_dir = root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    post_commit = hooks_dir / "post-commit"
    post_commit.write_text(
        "#!/bin/sh\n"
        "# Installed by Ledger — queues a spool event after every commit; never blocks git.\n"
        f'"{interpreter}" -m backend spool-commit --cwd "$(git rev-parse --show-toplevel)" >/dev/null 2>&1 &\n'
        "exit 0\n"
    )
    post_commit.chmod(0o755)

    claude_dir = root / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path = claude_dir / "settings.json"
    settings: dict[str, Any] = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            settings = {}
    hooks = settings.setdefault("hooks", {})
    start_command = f'"{interpreter}" -m backend session-start --cwd "$CLAUDE_PROJECT_DIR"'
    start_entry = {"matcher": "startup", "hooks": [{"type": "command", "command": start_command}]}
    end_command = f'"{interpreter}" -m backend session-end --cwd "$CLAUDE_PROJECT_DIR"'
    end_entry = {"matcher": "stop", "hooks": [{"type": "command", "command": end_command}]}
    # Idempotent: drop any prior Ledger entries before re-adding.
    kept_start = [e for e in hooks.get("SessionStart", []) if "backend session-start" not in json.dumps(e)]
    kept_end = [e for e in hooks.get("SessionEnd", []) if "backend session-end" not in json.dumps(e)]
    hooks["SessionStart"] = kept_start + [start_entry]
    hooks["SessionEnd"] = kept_end + [end_entry]
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")

    return {
        "repo": str(root),
        "post_commit": str(post_commit),
        "settings": str(settings_path),
        "interpreter": interpreter,
        "local_override": (claude_dir / "settings.local.json").exists(),
    }


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
