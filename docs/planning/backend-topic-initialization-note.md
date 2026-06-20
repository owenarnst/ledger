# Backend Topic Initialization Note

## Problem

The backend currently initializes Ledger by creating the SQLite schema and seeding one demo project plus fixed demo topics.

That is useful for the vertical slice, but it is not the intended long-term behavior. The backend should be responsible for creating real project/topic state from repository evidence, not only loading hardcoded sample rows.

## Current State

- App startup calls `LedgerRepository.initialize()`.
- `initialize()` creates the schema.
- If the database is empty, `_seed()` inserts:
  - one demo project
  - fixed demo topics
  - fixed evidence rows

The frontend then reads those stored rows through the API.

## Desired Direction

Replace demo-only topic seeding with backend-owned topic initialization that can:

- discover or register a real repository as a project
- collect repository evidence
- derive candidate topics from that evidence
- persist topics and evidence into SQLite
- revise or refresh topics when the repository changes

The backend should remain the source of truth for this workflow. The frontend should not create topics directly.

## Responsibility Boundary

Backend responsibilities:

- initialize schema and storage
- ingest repository metadata and evidence
- create and revise topics
- expose topics through the API
- create checks from persisted topics

Frontend responsibilities:

- request projects/topics/checks
- render topic detail and check state
- edit sandbox files
- trigger runs, coaching, and completion

## Suggested Transition

1. Keep `_seed()` only as an explicit demo/bootstrap path.
2. Add a backend initialization path for real projects.
3. Separate "schema initialization" from "demo seed" from "topic extraction."
4. Introduce a service that turns repository evidence into topic rows.
5. Add refresh/re-ingest behavior so topics can evolve with code changes.

## Minimal Refactor Goal

The first backend refactor should make this separation explicit:

- `initialize_schema()`
- `seed_demo_data()`
- `initialize_project_from_repo(...)`
- `extract_or_refresh_topics(...)`

That would make the current demo path honest while creating a clean place for the real Ledger topic pipeline.
