.PHONY: help dev frontend backend reset seed-demo extract extract-claude install install-frontend install-backend clean

REPO ?= $(HOME)/Projects/docs-search-api

help:
	@echo "Available commands:"
	@echo "  make dev          - Start both frontend and backend in development mode"
	@echo "  make frontend     - Start only the frontend dev server"
	@echo "  make backend      - Start only the backend dev server"
	@echo "  make reset        - Reset ~/.ledger to the curated Claude demo worklist (wipes DB + sandboxes, re-seeds the fixture)"
	@echo "  make seed-demo    - Alias for 'make reset' (the curated demo, incl. the tenant-isolation hero check, ships in the seed)"
	@echo "  make extract      - Discover the worklist for REPO via the deterministic analyst (default ~/Projects/docs-search-api); ingests the repo's real ~/.claude transcripts as Agent-trace recall"
	@echo "  make extract-claude - Same, but run the live Claude Code Topic Analyst (LEDGER_ANALYST=claude); it cites the real prompts + tool calls per topic"
	@echo "  make install      - Install all dependencies"
	@echo "  make install-frontend - Install frontend dependencies"
	@echo "  make install-backend  - Install backend dependencies"
	@echo "  make clean        - Clean build artifacts and node_modules"

dev:
	@echo "Starting frontend and backend..."
	@make -j2 frontend backend

frontend:
	@echo "Starting frontend dev server on http://localhost:4317"
	@cd frontend && npm run dev

backend:
	@echo "Starting backend dev server on http://localhost:8000"
	@. .venv/bin/activate && uvicorn backend.api:app --reload --port 8000 --host 0.0.0.0

# Wipes ~/.ledger and recreates it; backend.initialize() re-seeds the curated
# demo worklist (fixtures/demo_seed.json — verbatim live ClaudeAnalyst output)
# whenever the projects table is empty, so reset == a clean curated demo.
reset:
	@echo "Resetting Ledger to the curated Claude demo worklist..."
	@. .venv/bin/activate && python -m backend reset

# The curated demo bundles its hero check; there is no separate seed step, and a
# standalone seed on a non-empty DB collides on projects.slug. Reset is the path.
seed-demo: reset

extract:
	@echo "Discovering the worklist for $(REPO) (deterministic analyst)..."
	@. .venv/bin/activate && python -m backend extract --repo "$(REPO)"

extract-claude:
	@echo "Discovering the worklist for $(REPO) via the live Claude Code Topic Analyst..."
	@. .venv/bin/activate && LEDGER_ANALYST=claude python -m backend extract --repo "$(REPO)"

install: install-frontend install-backend

install-frontend:
	@echo "Installing frontend dependencies..."
	@cd frontend && npm install

install-backend:
	@echo "Installing backend dependencies..."
	@pip install -e ".[dev]"

clean:
	@echo "Cleaning build artifacts..."
	@rm -rf frontend/node_modules
	@rm -rf frontend/dist
	@rm -rf backend/__pycache__
	@rm -rf .pytest_cache
	@rm -rf ledger.egg-info
