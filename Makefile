.PHONY: install api web check lint types test fmt request
.DEFAULT_GOAL := help

help:  ## Show targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "%-14s %s\n", $$1, $$2}'

install:  ## Install dependencies
	uv sync

api:  ## Start the HTTP API on :8001
	uv run uvicorn app.api.main:app --port 8001

web:  ## Start the React dev server on :5173 (needs `make api`)
	cd web && npm install && npm run dev

check: lint types test  ## Lint, type-check and test

lint:  ## Ruff lint
	uv run ruff check .

fmt:  ## Ruff format
	uv run ruff format .

types:  ## Mypy
	uv run mypy

test:  ## Pytest (offline)
	uv run pytest -q

request:  ## Print a scripted order's model requests with token counts: make request CATALOG=catalog.json
	uv run --with tiktoken python -m tests.show_request $(CATALOG)
