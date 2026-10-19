.PHONY: install run api web check lint types test fmt
.DEFAULT_GOAL := help

help:  ## Show targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "%-14s %s\n", $$1, $$2}'

install:  ## Install dependencies
	uv sync

run:  ## Start the Streamlit chat UI
	uv run streamlit run app/ui/streamlit_app.py

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
