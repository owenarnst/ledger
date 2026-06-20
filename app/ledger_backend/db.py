from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    repo_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    provider TEXT NOT NULL DEFAULT 'claude_code',
    title TEXT NOT NULL,
    state TEXT NOT NULL,
    summary TEXT NOT NULL,
    why_now TEXT NOT NULL,
    risk_class TEXT NOT NULL,
    caller_count INTEGER NOT NULL,
    claude_authored INTEGER NOT NULL DEFAULT 0,
    rank INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id TEXT NOT NULL REFERENCES topics(id),
    provider TEXT NOT NULL DEFAULT 'claude_code',
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hook_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id),
    provider TEXT NOT NULL DEFAULT 'claude_code',
    event_type TEXT NOT NULL,
    branch TEXT,
    head_sha TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS checks (
    id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL REFERENCES topics(id),
    state TEXT NOT NULL,
    sandbox_path TEXT NOT NULL,
    target_file TEXT NOT NULL,
    test_command TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id TEXT NOT NULL REFERENCES checks(id),
    passed INTEGER NOT NULL,
    output TEXT NOT NULL,
    elapsed_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS coach_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id TEXT NOT NULL REFERENCES checks(id),
    question TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

MIGRATIONS = [
    "ALTER TABLE topics ADD COLUMN provider TEXT NOT NULL DEFAULT 'claude_code'",
    "ALTER TABLE evidence ADD COLUMN provider TEXT NOT NULL DEFAULT 'claude_code'",
    "ALTER TABLE hook_events ADD COLUMN provider TEXT NOT NULL DEFAULT 'claude_code'",
]


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for statement in MIGRATIONS:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc):
                raise
    conn.commit()
