.PHONY: help dev frontend backend install install-frontend install-backend clean

help:
	@echo "Available commands:"
	@echo "  make dev          - Start both frontend and backend in development mode"
	@echo "  make frontend     - Start only the frontend dev server"
	@echo "  make backend      - Start only the backend dev server"
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
