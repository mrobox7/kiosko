# Menu and ordering server

A FastAPI + Postgres server for one McDonald's outlet (Nemi Nagar, Jaipur): the menu with its
customisations, price checks, drive-thru orders and customers. It is meant to be called by a
voice agent. There is no payment and no dine-in.

## Run it

You need Docker and [uv](https://docs.astral.sh/uv/).

```bash
cd backend
docker compose up -d db          # Postgres on localhost:5434, database "restaurant"
uv sync                          # install dependencies
uv run python -m app.seed        # create the tables and load the menu (safe to repeat)
uv run uvicorn app.main:app --port 8010
```

The API is then at <http://localhost:8010>, with interactive docs at `/docs`.

| Setting | Default |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://menu:menu@localhost:5434/restaurant` |
| `TEST_DATABASE_URL` | `postgresql+psycopg://menu:menu@localhost:5434/restaurant_test` |

The tables are created with `create_all`, which adds missing tables but **never changes existing
ones**. There are no migrations. If a model changes, the matching table in the dev database has
to be dropped and recreated by hand, and the seed run again. `docker compose down -v` wipes the
whole database.

## Check it

```bash
uv run ruff check .
uv run mypy
uv run pytest -q
```

The tests need the database container running. They use their own `restaurant_test` database,
which is created if missing and rebuilt on every run, so the dev database is never touched.

## What it does

**Menu**

| | |
|---|---|
| `GET /products` | Items on the menu. Filters: `category` (slug), `veg` (true/false), `q` (text in name or description), `outlet` (outlet code) |
| `GET /products/{id}` | One item with its option groups (and the limits for that item), meal offers, nutrition and allergens. Takes `outlet` too |
| `GET /catalog` | The whole menu in one response, with a `version` that changes when anything in it changes. Takes `outlet` too |
| `GET /catalog/version` | Only the `version` of `/catalog` (takes `outlet`), to check whether a copy is out of date |
| `GET /images/{file}` | The product pictures (`image_url` on a product points here) |

**Outlets.** Each outlet has a short `code` (the Nemi Nagar one is `JPR-013-7429`). A drive-thru
is set up once with its code, and everything it sends names the outlet by that code: `outlet` in
`POST /orders` and `POST /orders/price`, and `?outlet=` when reading the menu. With `?outlet=`,
items that outlet is not selling are left out. Without it you get the menu as loaded, with
nothing left out. An unknown code is a 404. The menu is the same everywhere; an outlet only records
what it cannot sell right now. A product it is not selling is a row in `unavailable_products`, and
an option it is not offering (a drink it has run out of) is a row in `unavailable_options`. Delete
the row to sell it again. Prices are the same at every outlet.

The point-of-sale switches things off and on (not the voice agent):

| | |
|---|---|
| `GET /outlets/{code}/unavailable` | The product ids and option ids the outlet is not selling now |
| `PUT /outlets/{code}/unavailable/products/{id}` | Stop selling a product (204; doing it twice is fine) |
| `DELETE /outlets/{code}/unavailable/products/{id}` | Sell it again |
| `PUT` / `DELETE /outlets/{code}/unavailable/options/{id}` | The same for an option |

What follows from those switches, so the menu never offers what the outlet cannot make:
- an option that points at a product (a combo's "choose a burger") goes when that product is off;
- a product with a required question that has no answers left goes too (a combo whose every burger
  choice is off); a meal upgrade goes when its side or drink question has none left;
- ordering one of these is refused with an `unavailable` problem, both when it is added and again
  when the order is placed.

Items that are in a combo's name only (the fries in "burger + fries + puffs") are not separate rows,
so the server cannot know they are gone. To stop such a combo, switch the combo itself off.

**Pricing**

| | |
|---|---|
| `POST /orders/price` | Check a cart against the menu and price it. Nothing is saved. |

The answer has `ready` (true when nothing is missing and nothing is wrong), the priced lines,
`subtotal`, `gst`, `total`, and two lists: `missing` (required questions not answered yet, so
ask the customer) and `problems` (something is wrong and must change).

**Orders**

| | |
|---|---|
| `POST /orders` | Start a draft (the cart) at an `outlet` (its code). A `customer_id` is optional. |
| `POST /orders/{id}/lines` | Add one item. It must be complete and valid, otherwise 422 with `missing` and `problems`, and nothing is saved. |
| `DELETE /orders/{id}/lines/{line_id}` | Remove a line. To change a line, remove it and add it again. |
| `PATCH /orders/{id}/lines/{line_id}` | Change a line's `quantity` only; the line keeps its id and price |
| `DELETE /orders/{id}` | Abandon a draft (started over, left, timed out). It is kept with status `cancelled` and can no longer change. Repeating it is fine; a confirmed order is 409. |
| `PUT /orders/{id}/customer` | Put a draft on a customer, for when they are identified after ordering began |
| `GET /orders/{id}` | The order with its lines and totals |
| `POST /orders/{id}/confirm` | Check everything again against the menu as it is now, then freeze the order and give it its number |

A confirmed or cancelled order cannot change. A cancelled cart is not offered back by
`/customers/{id}/draft` and is not in their order history. Confirm refuses an empty order (409), an item that is no longer
available (409, the order stays a draft), and a price that changed since the line was added (409
with a `price_changed` problem; the lines are updated to the new price, so confirming again
accepts it).

**Errors.** Every error from the server has the body `{"detail": {"code": "...", "message": "..."}}`.
The `code` is for programs and the `message` is for people. The codes are `not_found` (404),
`order_closed` (409, the order is already confirmed or cancelled), `empty_order` (409),
`invalid_line` (422, an item that is incomplete or wrong) and `cannot_confirm` (409). The last two
also carry `missing` and `problems` lists; each `problem` has its own `code` (`unavailable`,
`price_changed`, `no_such_meal`, ...). The one exception is a request that is not shaped right
(a missing field, a text where a number belongs): FastAPI answers 422 with its own list of
field errors.

The order number is the short number called out at the window. It counts 1, 2, 3 for each outlet
and restarts every day (India time).

**Customers**

| | |
|---|---|
| `POST /customers` | Find the customer by mobile number, or add them. 201 when new, 200 when known. Only `phone` is required. |
| `GET /customers/{id}` | The customer |
| `PATCH /customers/{id}/preferences` | Merge keys into the preferences (diet, allergies, anything). Other keys stay. |
| `GET /customers/{id}/orders` | Confirmed orders, newest first (`limit`) |
| `GET /customers/{id}/favourites` | Most ordered items still on the menu (`limit`) |
| `GET /customers/{id}/draft` | The latest unfinished cart that has items in it, or 404 |

Phone numbers are Indian mobiles and are stored as `+91` and ten digits. `98765 43210`,
`09876543210` and `+91 98765 43210` all find the same customer.

## A short example

```bash
curl localhost:8010/products/3                       # McSpicy Chicken: groups, options, ids
curl -X POST localhost:8010/orders/price -H 'content-type: application/json' -d '
  {"outlet": "JPR-013-7429", "lines": [{"product_id": 3, "quantity": 2,
     "options": [{"option_id": 1}, {"option_id": 5}]}]}'   # ketchup + double cheese
curl -X POST localhost:8010/orders -H 'content-type: application/json' -d '{"outlet": "JPR-013-7429"}'
# the answer has the new order's "id"; below it is 1, use yours
curl -X POST localhost:8010/orders/1/lines -H 'content-type: application/json' -d '
  {"product_id": 3, "options": [{"option_id": 1}, {"option_id": 5}]}'
curl -X POST localhost:8010/orders/1/confirm
```

The ids (product 3, options 1 and 5) come from the seed; read them from `/products/{id}`.

## How an item is priced

```
unit price = base price (or the outlet's override)
           + the meal's extra price (only if a meal size is chosen)
           + the chosen options' price changes (price x qty)
line total = unit price x quantity
```

Customisation is questions (option groups) with answers (options). A product asks some groups.
Each group has a minimum and maximum number of picks, and a product can override them. A
"make it a meal" upgrade (Medium or Large) adds a side and a drink question; a Large meal has no
side. Options can also point at other products, as in a combo's "choose a burger".

Prices are exact decimal rupees, **before tax**. GST is 5%, worked out once on the order total and
rounded half-up to the paisa. It lives in one function, `pricing.gst`. The server is the only
place that adds prices up. The API sends prices as plain JSON numbers.

## The data

`seed/seed.json` holds the menu: 110 products in 8 categories, 67 option groups, 169 options and
48 meal offers, with their images in `static/images/`. Prices come from a delivery app's menu
for this outlet and may differ from in-store prices. Rows are matched by id, so editing the file
and running the seed again updates the database. Rows removed from the file are not deleted from
the database.

Calories for 42 products are from the menu. **All other calories, all macros (protein, fat,
carbs, sugar, sodium) and all allergen lists are general estimates**, filled in by item type, and
not lab or official figures. An empty allergen list means none is listed, not that the item is
verified allergen-free.

The images are McDonald's assets. Keep them out of any public repository.

## What it does not do

- No login. A customer is whoever gave that mobile number; nothing proves they own it. There is
  no API key either.
- No payment, no cancelling a placed order, no editing a line beyond its quantity.
- No pickup time, opening hours, time-of-day menus or stock counts.
- No endpoint to edit the menu. Change the seed file or the database.
- Drafts never expire on their own: whoever owns the session cancels the draft when the customer
  leaves or times out. Two simultaneous edits to one cart can clash; only the order number is
  protected by a lock.
- No quantity limit on a line.

## Layout

Code is grouped by topic. Each topic folder holds its own tables, API shapes, logic and URLs.

```
app/
  main.py           the app and error handling
  database.py       connection, session, create_tables
  seed.py           loads seed/seed.json
  menu/             categories, products, options, meal offers, outlets
    models.py  schemas.py  service.py  router.py
    availability.py  what one outlet sells
  orders/           orders, their items, pricing
    models.py  schemas.py  service.py  pricing.py  router.py
  customers/        customers, preferences, history, favourites, resuming a cart
    models.py  schemas.py  service.py  router.py
seed/seed.json      the menu data
static/images/      product pictures
tests/              API and seed tests, against a real Postgres
```

`orders` depends on `menu` (items point at products and options). `customers` reads `orders`
for history and favourites. `menu` depends on nothing.
