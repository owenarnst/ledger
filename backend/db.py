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
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS commits (
    sha TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    parent_sha TEXT,
    committed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    provider TEXT NOT NULL,
    source_path TEXT,
    started_at TEXT,
    ended_at TEXT,
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
    checkable INTEGER NOT NULL DEFAULT 0,
    rank INTEGER NOT NULL,
    impact_level TEXT,
    impact_consequence TEXT,
    priority_rationale TEXT
);

CREATE TABLE IF NOT EXISTS topic_revisions (
    id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL REFERENCES topics(id),
    revision INTEGER NOT NULL,
    commit_sha TEXT,
    code_path TEXT NOT NULL,
    invariant TEXT NOT NULL,
    risk_class TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(topic_id, revision)
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id TEXT NOT NULL REFERENCES topics(id),
    provider TEXT NOT NULL DEFAULT 'claude_code',
    session_id TEXT REFERENCES sessions(id),
    source_path TEXT,
    tool_sequence_json TEXT NOT NULL DEFAULT '[]',
    link_confidence TEXT NOT NULL DEFAULT 'heuristic',
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    excerpt_sha TEXT,
    relevance TEXT
);

CREATE TABLE IF NOT EXISTS revision_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_revision_id TEXT NOT NULL REFERENCES topic_revisions(id),
    evidence_id INTEGER NOT NULL REFERENCES evidence(id),
    role TEXT NOT NULL,
    confidence TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS topic_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id TEXT NOT NULL REFERENCES topics(id),
    topic_revision_id TEXT REFERENCES topic_revisions(id),
    event_type TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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

CREATE TABLE IF NOT EXISTS reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id TEXT NOT NULL REFERENCES checks(id),
    topic_id TEXT NOT NULL REFERENCES topics(id),
    topic_revision_id TEXT REFERENCES topic_revisions(id),
    invariant TEXT NOT NULL,
    rationale TEXT NOT NULL,
    future_risk TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS checks (
    id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL REFERENCES topics(id),
    topic_revision_id TEXT REFERENCES topic_revisions(id),
    state TEXT NOT NULL,
    sandbox_path TEXT NOT NULL,
    target_file TEXT NOT NULL,
    test_command TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS check_recipes (
    id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL REFERENCES topics(id),
    topic_revision_id TEXT REFERENCES topic_revisions(id),
    fixture_source TEXT NOT NULL,
    revision_sha TEXT,
    target_file TEXT NOT NULL,
    target_test TEXT,
    test_command TEXT NOT NULL,
    mutation_before TEXT NOT NULL,
    mutation_after TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(topic_id)
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

-- One row per Topic Analyst discovery run. Makes an agentic worklist auditable:
-- which model proposed it, against what input, and how verification adjudicated
-- its citations (ADR-0002 "auditable and reproducible enough to debug").
CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id),
    analyst_model TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    input_scope_json TEXT NOT NULL DEFAULT '{}',
    raw_output TEXT NOT NULL DEFAULT '',
    proposed_count INTEGER NOT NULL DEFAULT 0,
    verified_count INTEGER NOT NULL DEFAULT 0,
    rejected_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

MIGRATIONS = [
    "ALTER TABLE topics ADD COLUMN provider TEXT NOT NULL DEFAULT 'claude_code'",
    "ALTER TABLE evidence ADD COLUMN provider TEXT NOT NULL DEFAULT 'claude_code'",
    "ALTER TABLE hook_events ADD COLUMN provider TEXT NOT NULL DEFAULT 'claude_code'",
    "ALTER TABLE checks ADD COLUMN topic_revision_id TEXT REFERENCES topic_revisions(id)",
    "ALTER TABLE evidence ADD COLUMN session_id TEXT REFERENCES sessions(id)",
    "ALTER TABLE evidence ADD COLUMN source_path TEXT",
    "ALTER TABLE evidence ADD COLUMN tool_sequence_json TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE evidence ADD COLUMN link_confidence TEXT NOT NULL DEFAULT 'heuristic'",
    "ALTER TABLE reflections ADD COLUMN topic_revision_id TEXT REFERENCES topic_revisions(id)",
    "ALTER TABLE projects ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE topics ADD COLUMN checkable INTEGER NOT NULL DEFAULT 0",
    # Repo-derived recipes pin a real commit and the test the mutant must break;
    # fixture-based demo recipes leave both NULL.
    "ALTER TABLE check_recipes ADD COLUMN revision_sha TEXT",
    "ALTER TABLE check_recipes ADD COLUMN target_test TEXT",
    # ADR-0002: verified excerpts carry their hash + the analyst's relevance note;
    # topics carry the analyst's grounded impact + priority explanation.
    "ALTER TABLE evidence ADD COLUMN excerpt_sha TEXT",
    "ALTER TABLE evidence ADD COLUMN relevance TEXT",
    "ALTER TABLE topics ADD COLUMN impact_level TEXT",
    "ALTER TABLE topics ADD COLUMN impact_consequence TEXT",
    "ALTER TABLE topics ADD COLUMN priority_rationale TEXT",
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
