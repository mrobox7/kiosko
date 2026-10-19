# DishPatch: rules for Claude

## Never without explicit permission
Ask first, say what the action will touch, and wait for a yes. A yes covers that one action, not later ones.

- **Destructive actions:** deleting or overwriting files, `git reset`, `git clean`, `git checkout` over changes, `git stash`, `rm -rf`, dropping data, `docker compose down -v` (it wipes the database).
- **Committing:** no `git commit`, `git push`, branch changes, tags, amends or force pushes. All work may be uncommitted; treat it as the only copy.
- **Deleting:** no deleting files, folders, branches, database rows, published artifacts or anything else.
- **Anything online that changes something or costs something:** pushing, publishing, deploying, creating or editing remote resources, and live calls to Groq or Sarvam, which spend quota. Say how many requests you will make first.

Reading is fine without asking: `git status`, `git diff`, `git log`, reading files, running offline tests, linting and type checks.

## Working rules
- Consult the user before any decision. Recommend one option, don't survey, and wait.
- Keep `.env` and API keys private. Never print them.
- To check whether a test is flaky, run it repeatedly on the current tree. Never change repository state to compare.
- Say plainly what you did and what you did not verify. Don't claim a result you did not see.

## Project checks
Run before reporting work done: `uv run ruff check .`, `uv run mypy app`, `uv run pytest -q`; for `web/`: `npm run build` and `npx oxlint`.
