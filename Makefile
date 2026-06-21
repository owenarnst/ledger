.PHONY: help dev frontend backend seed-demo extract extract-claude curate-hero install install-frontend install-backend clean

REPO ?= $(HOME)/Projects/docs-search-api

help:
	@echo "Available commands:"
	@echo "  make dev          - Start both frontend and backend in development mode"
	@echo "  make frontend     - Start only the frontend dev server"
	@echo "  make backend      - Start only the backend dev server"
	@echo "  make seed-demo    - Install the curated demo project (the app no longer seeds it implicitly)"
	@echo "  make extract      - Discover the worklist for REPO via the deterministic analyst (default ~/Projects/docs-search-api)"
	@echo "  make extract-claude - Same, but run the live Claude Code Topic Analyst (LEDGER_ANALYST=claude)"
	@echo "  make curate-hero  - Install the validated repo-derived tenant-isolation check for REPO"
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

seed-demo:
	@echo "Installing the curated demo project..."
	@. .venv/bin/activate && python -m backend seed-demo

extract:
	@echo "Discovering the worklist for $(REPO) (deterministic analyst)..."
	@. .venv/bin/activate && python -m backend extract --repo "$(REPO)"

extract-claude:
	@echo "Discovering the worklist for $(REPO) via the live Claude Code Topic Analyst..."
	@. .venv/bin/activate && LEDGER_ANALYST=claude python -m backend extract --repo "$(REPO)"

curate-hero:
	@echo "Installing the validated repo-derived check for $(REPO)..."
	@. .venv/bin/activate && python -m backend curate-hero --repo "$(REPO)"

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
