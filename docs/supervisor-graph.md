# Supervisor graph (proposal)

A newer approach to the same problem. Written from the design discussion and `graph.excalidraw`;
nothing here is implemented and it is deliberately not tied to the current graph.

## Shape

One **Supervisor** understands the customer's message and writes the reply. Two workers do the
rest: the **Searcher** turns vague requests into candidates, the **Executor** changes the order.
Which one runs next is decided by a **router in code**, reading item statuses. No model chooses.

```
START → supervisor → router ─┬→ searcher → router
                             ├→ executor → respond → END
                             └→ respond  → END
```

`supervisor` may finish the turn itself (see `reply` below), skipping `respond`.

Model calls per turn: one for chat; two when workers run (supervisor + respond); plus the
Searcher's own call when it is needed.

## The Item

One typed list is the contract between every node. It is saved between turns, so an unanswered
question survives to the next message.

| field | meaning |
|---|---|
| `id` | stable, so a later reply can update the same item |
| `kind` | `add`, `remove`, `change_qty`, `place`, `cancel`, `search`, `chat` |
| `dish_text` | what the customer said |
| `dish_id` | set by code once the text matches a real dish |
| `qty`, `options`, `meal_size`, `note` | as said; `meal_size` only when they asked for the meal |
| `target_line` | for `remove` / `change_qty`: an order line id |
| `status` | see below |
| `question`, `candidates` | set when the customer must choose |
| `result` | set when done or failed; a search answer lives here |

### Statuses

- `ready`: has everything its tool needs.
- `needs_search`: the text is vague or matches no dish; the Searcher must run.
- `needs_user`: several dishes fit, or the Searcher found candidates; the customer must choose.
- `done` / `failed`: the Executor or Searcher has finished it. Only `needs_user` is kept between
  turns.

Only code sets `dish_id` and `status`. The model proposes text.

### Matching text to a dish

Done in code, with no model, in `app/menu/fuzzy.py` (standard library `difflib` only). Each
dish is scored against `dish_text` with spaces ignored, so spoken "mc aloo tikki" finds "McAloo Tikki
Burger". Whole name scores 1; part of a name scores by how much of it was said; near spellings
score by similarity.

- **Combos** (`kind == "combo"`, the `meals` category) are candidates only if the customer said
  "meal" or "combo". So "mc aloo tikki" means the burger, and "happy meal mcaloo tikki" means the
  Happy Meal.
- Whole name, and nothing else is a whole-name match → `ready`.
- Else best score ≥ 0.85 and at least 0.10 ahead of the next → `ready`.
- Else dishes scoring ≥ 0.6 (at most 3) → `needs_user`, put to the customer ("mc flurry": which
  flavour?). A wrong dish on an order is worse than a question.
- Else → `needs_search` (not a dish name: "a drink", "pizza").

The thresholds were checked by hand against the real seed menu (27 phrases), not tuned on data.
Not handled: spellings far from the name ("alu tikki" scores 0.56 and goes to the Searcher).
Options (sizes, "no ketchup") and order lines still use the matcher in `app/menu/lookup.py`.

## Router (code, no model)

Evaluated in this order after every node:

1. Any `needs_search` item → **searcher**, then back to the router.
2. Else any `ready` item → **executor**, then **respond**.
3. Else → **respond**.

**Run what is clear.** The executor runs every `ready` item now. An item that still needs the
customer (`needs_user`) does not hold the others back; only the question is kept for the next
turn. The one exception is `place` and `cancel`: while any other item is `needs_search` or
`needs_user` they are not run, and they are not kept either. They are reported as "not done yet",
so a later turn never places an order the customer may have changed their mind about.

Each item moves through its statuses once, so the graph cannot loop.

## Supervisor

### Call 1: record the request (structured output)

```
{
  "language": "en | hi | hinglish",
  "items":   [ new things asked for ],
  "updates": [ {id, dish_text? | qty? | options? | note? | drop?} ],
  "reply":   optional text, only for chat / answerable from State
}
```

- `updates` refer to open items from earlier turns by id. This is how "coke" answers an open
  "which drink?" item.
- `reply` lets a chat turn, or one the State already answers, finish in this single call. Every
  other turn gets its reply from call 2.
- The model never writes dish ids or statuses. For `remove` / `change_qty` it names the order
  line from the lines in its context, and code checks that the line exists.

Context for call 1:

- Fixed system text plus the **menu card** (cacheable). The card (`app/menu/card.py`) has
  one line per section: its name, the slug the menu tools take, the diets it serves (computed from
  the data) and up to 5 of its dishes (bestsellers first), with "(+N more)" when the list is
  partial. About 258 tokens on the real menu, against about 587 for the full outline. Because the
  lists are partial, the prompts say a dish missing from the card may still be sold. Names are
  resolved in code, so the model does not need the list. The full outline (`Menu.outline`) is
  untouched and still used by the older graph.
- The current order: lines with ids, quantities, options.
- Open items: id, question, candidates.
- The last turn or two, plus the summary.
- Customer, allergies, outlet.

### Call 2: respond

Runs only when call 1 returned no `reply`. Output: the reply text, streamed.

The model is never given items, ids, statuses or result fields. Code writes a **turn report**
(`turn_report` in `context.py`) from the items and the order: one plain statement per line, each
with a label.

| label | meaning |
|---|---|
| `ORDER` | open and not placed / placed / cancelled, and the dishes on it |
| `DONE` | something that really happened this turn |
| `ASK` | a question the system puts to the customer itself, after the reply; the model never asks it |
| `ANSWER` | the answer to a menu question |
| `SHOW` | the system reads the order out right after the reply |
| `NOT SOLD` | a dish that is not on the menu, and what is close |
| `NOT DONE` | something waiting on open questions (place or cancel) |
| `FAILED` | something that went wrong; for a lookup, a technical problem, never "not sold" |
| `CHANGES` | whether anything changed |

The reply is phrased from those lines alone. It may not claim anything no line says, and it
never writes a quantity, price, total or order number: code appends the order summary (see
`order_summary.py`) when the order changed, was placed, or the customer asked to hear it
(`show_order`). Code also appends every open question (`open_questions` in `context.py`), after
the summary: a missing size or sauce (named for its dish by `add_to_order`), a phone read-back, a
"which one?". The model only acknowledges, so a question is never left out or put about the wrong
dish. Internal markers in an item's `result` are codes (`LOOKUP_DOWN`, `HELD` in
`items.py`), never English, so no internal wording can reach a customer.

All three prompts share one shape: ROLE, INPUT, RULES, OUTPUT, SUCCESS. A test checks it, and
another checks that every label the report uses is explained in the reply prompt.

## Searcher (LLM agent)

- Input: items with `needs_search`. It is given **no menu card**: the card is for `supervisor`, to
  avoid a search when it can. The Searcher has the real tools, so it starts with `get_menu` (no
  filter lists the sections) and may say only what tool results show.
- Tools: `get_menu` (filters), `get_item`, and `finish`, which ends the search.
- Informational search → the answer text goes in `result`; item is `done`.
- Order item → candidate dish ids; item becomes `needs_user` with a question and `candidates`.
- The dish exists but which one is unclear → `needs_user` with the matching names (`available`
  true). The customer must choose.
- The dish is not on the menu → `failed`, with `not_on_the_menu` and the closest names as
  alternatives (`available` false). The reply says so and offers them; nothing is held back.
- Never sets `ready`. Even a single result for a vague request asks "did you mean X?".
- At most 2 tool rounds per item; then it stops and asks the customer.

## Executor (plain code)

- Input: `ready` items, in the order the customer said them.
- Runs the tool each `kind` maps to: add, remove, change qty, place, cancel.
- Each item ends `done` or `failed` with the tool's result; one failure does not stop the others.
- Runs the clear items even when another item is waiting for the customer; see the router.
- No model: a typed `ready` item already holds a dish id, quantity and option ids, so choosing the
  tool is a lookup. A model here could only pick the wrong tool or quantity.

## Contracts between nodes

- The saved state holds the item list; nodes read it and return partial updates.
- Validate at the boundary: the Supervisor's output is parsed into the `Item` model before it
  enters state, and a failed parse is retried or falls back to a clarifying reply.
- The router may check the contract before routing and send bad data to a repair path.

## As built

Differences from the plan above, and what was left out:

- **Native tool calling everywhere the model acts.** `LLMClient.complete` takes optional `tools`
  and `require_tool`; replies carry `tool_calls`; results go back as `tool_outcomes` (additive, so
  the older graph is unaffected). `supervisor` must call one tool, `record_request`, whose schema
  is the `Understanding` model. The Searcher is offered `get_menu`, `get_item` (the real tools,
  dispatched through `ToolRegistry`) and `finish`. Every call the model makes is answered, up to
  two menu rounds, and the last round offers only `finish`. `respond` stays plain text and the
  Executor stays plain code, so neither has a fake action.
  An earlier version had the Searcher write JSON as text; with `gpt-oss-120b` on Groq the model
  tried its own built-in tool instead and Groq returned a 400.
- **A server question is a question:** if the order server refuses an add as `incomplete` (a
  required choice is missing), the item becomes `needs_user` with the server's question, not
  `failed`. Items that ran before it stay done.
- **`dish_text` has no filler words.** The matcher needs every word to be in a dish name, so the
  prompt tells the model to drop "a", "the", "two", "please".
- **History** is the last 3 turns word for word. There is no running summary.
- **Not built:** the confirmation gate for place and cancel (by request), a running summary of older
  turns (the last 3 turns are kept word for word).
- **Streaming:** `respond` streams through `context={"on_text": ...}`, then the order summary is
  passed to the same callback. A reply that `supervisor` gives itself (an all-chat turn) is returned
  whole, not streamed.

## Contract with the session

The graph is a drop-in for what `Session` and the API read from the old one:

- **Input:** `{"kind": "start"}` opens a chat with no model call (stop_reason `started`);
  `{"kind": "message", "user_text", "spoken"}` is a turn.
- **Output:** `reply`, `stop_reason`, `events`, `order`, `status` (`open`, `placed`, `abandoned`).
- **Nodes:** `guard -> supervisor -> (searcher) -> (executor) -> respond -> commit`. `commit` is
  also the node name the session writes state as for a tap on the screen or an abandoned chat.
- **Guard** (`nodes/guard.py`): refuses an empty or too long message, a rate above `turns_per_min`, and a
  chat past its `token_budget`, each with a canned reply and no model call.
- **Trace events** (`trace.py`): `GuardDecided`, `LLMCalled` (tokens, cached tokens, latency),
  `ItemsRecorded`, `ActionRun` (per item, with latency), `TurnEnded`. `Tally`, in the same file, adds an
  event and the tokens for every model call.
- **Phone and needs:** item kinds `phone` and `need` run `set_customer` and `note_need`. A number is
  read back first ("I heard 9 8 7... Is that right?") and taken only after a yes, because
  `set_customer` requires `digits_confirmed`.
- **Voice:** a spoken turn adds the voice rules to the reply prompt, and the order summary is read
  in words.
- **Order summary** (`order_summary.py`): when the order changed this turn or was placed, code appends
  the lines, the total and the order number from the order the server returned. The reply writer
  is shown no price, quantity total or order number, so none in a reply is the model's.

## Open questions

1. **Wiring:** done. `runtime.py`, `Session` and `api/` use this package, and `app/` no longer
   imports `app.agent`. The old folder and the tests of its internals are the only things left
   that use it.
2. **Hot / cold drinks** are not on the card: the menu data has no such field.
3. **Hinglish and far spellings** of dish names go to the searcher.
4. **Order of operations:** searches run before changes; a change that depends on an earlier change
   in the same message is not covered.
5. **Place / cancel:** no confirmation check, by request.
6. **The Searcher has no name search.** In a live run "do you have pizza?" was answered "no"
   although `Pizza McPuff 2PC Meal` exists, because `get_menu` cannot search by name.
