.DEFAULT_GOAL := help

BACKEND := backend
FRONTEND := frontend
UV_SYNC := cd $(BACKEND) && uv sync
UV := cd $(BACKEND) && uv run
NPM := npm --prefix $(FRONTEND)

.PHONY: help install install-backend install-frontend \
        dev dev-backend dev-frontend \
        lint lint-backend lint-frontend \
        format format-backend \
        typecheck typecheck-backend typecheck-frontend \
        test test-backend \
        check build build-frontend \
        clean

help: ## Show this help
	@echo "Available targets:"
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

## --- Setup ---------------------------------------------------------------

install: install-backend install-frontend ## Install backend + frontend dependencies

install-backend: ## Install backend dependencies via uv
	$(UV_SYNC)

install-frontend: ## Install frontend dependencies via npm
	$(NPM) install

## --- Dev servers -----------------------------------------------------------

dev-backend: ## Run FastAPI backend with autoreload (127.0.0.1:8000)
	$(UV) uvicorn loregraph.main:app --reload --host 127.0.0.1 --port 8000

dev-frontend: ## Run Vite frontend dev server
	$(NPM) run dev

## --- Lint / format ---------------------------------------------------------

lint: lint-backend lint-frontend ## Lint backend (ruff) + frontend (oxlint)

lint-backend: ## Lint backend with ruff
	$(UV) ruff check .

lint-frontend: ## Lint frontend with oxlint
	$(NPM) run lint

format: format-backend ## Format backend with ruff

format-backend: ## Format backend code with ruff
	$(UV) ruff format .
	$(UV) ruff check --fix .

## --- Type checking -----------------------------------------------------------

typecheck: typecheck-backend typecheck-frontend ## Type-check backend (mypy) + frontend (tsc)

typecheck-backend: ## Type-check backend with mypy
	$(UV) mypy .

typecheck-frontend: ## Type-check frontend with tsc
	$(NPM) run typecheck

## --- Tests -------------------------------------------------------------------

test: test-backend ## Run backend test suite

test-backend: ## Run backend tests with pytest
	$(UV) pytest

## --- Build / aggregate checks -------------------------------------------------

check: lint typecheck test ## Run lint + typecheck + tests (pre-commit-equivalent gate)

build-frontend: ## Build frontend production bundle
	$(NPM) run build

build: build-frontend ## Build production artifacts

## --- Cleanup -------------------------------------------------------------------

clean: ## Remove build artifacts and caches
	rm -rf $(BACKEND)/.mypy_cache $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache
	find $(BACKEND) -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf $(FRONTEND)/dist
