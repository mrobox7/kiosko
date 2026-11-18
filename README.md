# Kiosko

Drive-thru ordering agent. Each customer message runs one LangGraph turn (`app/agent/graph.py`):
guard (plain code), supervisor (one model call that records what the customer asked for as typed
items), then a router in code that sends the turn to the searcher (the model looks at the menu with
tools), the executor (code that makes the clear changes to the order, with no model), and respond
(one model call that writes the reply; code adds the order summary), and finally commit. The design
and the reasons for it are in `docs/supervisor-graph.md`.

## Layout

```
app/
  runtime.py       builds the real services once per process
  config/          settings.py (environment) · observability.py (logfire)
  backend/         client.py (the only HTTP client for the restaurant backend) · errors.py · models.py
  menu/            everything that knows the menu: menu.py (cached, reloaded on version change) ·
                   names.py · lookup.py (exact names -> ids) · fuzzy.py (spoken words -> dish) ·
                   card.py (the short summary in prompts) · questions.py (a dish's questions)
  llm/             contract.py · messages.py · tool_spec.py · openai_compat.py
  speech/          contract.py · sarvam.py · sarvam_stream.py · sentences.py · spoken_turn.py
  tools/           what the model or a screen tap can do
                   contract.py (Tool, ToolContext, ToolResult) · registry.py · backend_errors.py
                   order/ (add, remove, change quantity, place, cancel) · customer/ · menu/
  agent/           the ordering graph: graph.py · state.py · items.py · services.py · router.py ·
                   prompts.py · context.py · order_summary.py · trace.py · tool_context.py
                   nodes/ (guard, supervisor, searcher, executor, respond, commit)
                   utils/ (classify_item.py: an item's words -> ids and a status)
  session/         session.py (one chat over the graph) · store.py (chats held in memory)
  api/             app.py (routes) · kiosk.py · voice.py · schemas.py · main.py
tests/             mirrors app/; support/ holds the fakes (order server, speech, LLM)
```

Packages depend one way: `llm`, `backend` -> `menu` -> `tools` -> `agent` -> `session` -> `api`.

## Setup
1. Start the backend in `backend/` (its README has the details): `docker compose up -d db`,
   `uv run python -m app.seed`, `uv run uvicorn app.main:app --port 8010`; check
   `curl localhost:8010/health`. `OUTLET_CODE` in `.env` names the outlet (the seed has `JPR-013-7429`).
2. `make install`, then copy `.env.example` to `.env` and set `LLM_API_KEY`.
3. Checks: `make check` (lint, types, tests).
4. Run the web app: `make api` (Python API on :8001) and, in a second terminal, `make web`
   (React on :5173, which forwards `/api` to the API). Open http://localhost:5173.
   `make help` lists all targets. The dish pictures come from the ordering server, so the page
   forwards `/images` to it as well (`BACKEND_URL`, default http://localhost:8010).

The page is a drive-thru kiosk styled after the reference redesign (`~/Downloads/mcd_ui_ref`): touch
to start, a home screen with category tiles and popular dishes, "My Order" always beside the menu,
a sheet per dish for its meal and options, then a green review screen before the order is placed.
"Ask Kiosko" opens the chat and voice assistant over the same order, so taps and talk can be
mixed. It works in landscape and portrait, in light and dark (dark at night by the clock, or the
switch on the start screen). Colours, radii and fonts are named values in `web/src/index.css`;
the logo is `web/public/logo.png`.

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
