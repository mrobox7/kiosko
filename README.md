# DishPatch

Restaurant reception agent (see PLAN.md).

## Setup
1. Start the backend: `docker compose up -d --build` in `restaurant-api/`; check `curl localhost:8000/health`.
2. `make install`, then copy `.env.example` to `.env` and set `LLM_API_KEY`.
3. Checks: `make check` (lint, types, tests).
4. Run: `make run`. `make help` lists all targets.

## Assumptions
- OpenAI-compatible chat API with native tool calling (default: Groq `openai/gpt-oss-120b`).
- Restaurant time zone defaults to `Asia/Kolkata`; datetimes are naive ISO 8601.
- Backend contract: `docs/backend-contract.md`.
