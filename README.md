# DishPatch

Restaurant reception agent (see PLAN.md).

## Setup
1. Start the backend: `docker compose up -d --build` in `restaurant-api/`; check `curl localhost:8000/health`.
2. `make install`, then copy `.env.example` to `.env` and set `LLM_API_KEY`.
3. Checks: `make check` (lint, types, tests).
4. Run the web app: `make api` (Python API on :8001) and, in a second terminal, `make web`
   (React on :5173, which forwards `/api` to the API). Open http://localhost:5173.
   The older Streamlit page is still there: `make run`. `make help` lists all targets.

Voice (needs `SARVAM_API_KEY`): a mic button appears next to Send. Tap to record and tap to
send, or turn on hands-free (headset button): it listens continuously and you can speak over
the agent to interrupt it. Headphones work best, since the browser has to tell your voice from
the agent's. Restart `make api` after pulling changes: it does not reload by itself.

The API holds chats in memory and the session id is the only credential: a prototype, not a
production setup.

## Assumptions
- OpenAI-compatible chat API with native tool calling (default: Groq `openai/gpt-oss-120b`).
- Restaurant time zone defaults to `Asia/Kolkata`; datetimes are naive ISO 8601.
- Backend contract: `docs/backend-contract.md`.
