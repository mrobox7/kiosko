# Backend contract (verified against the running API, 2026-10-17)

Full schema: `backend-openapi.json`. Base URL `http://localhost:8000`. Datetimes are naive ISO 8601.

## Endpoints used
| Stage | Endpoint | Notes |
| --- | --- | --- |
| 1 | `GET /menu` | query: `category`, `tags_any`, `tags_all`, `exclude_tags`, `max_price`, `available_only` |
| 2 | `GET /availability` | `slot_datetime`, `party_size`, `location`; returns `available_tables[{table_id, table_number, capacity, location}]` |
| 2 | `GET /customers/lookup` (`phone` or `email`), `POST /customers` | create takes `name`, `phone`, `email`, `preferences` |
| 2 | `POST /reservations` | `customer_id, table_id, slot_datetime, party_size, special_requests?` -> 201 |
| 2 | `GET/DELETE /reservations/{id}`, `GET /customers/{id}/reservations?status=` | |
| 2 | `POST/GET /reservations/{id}/orders`, `DELETE /orders/{id}` (204) | order body `menu_item_id, quantity` |
| 3 | `GET /customers/{id}`, `PATCH /customers/{id}/preferences`, `GET /customers/{id}/orders` | patch body `{"preferences": {...}}` |

## Models
- MenuItemOut: `id, name, description, price, tags[], category, available`
- Tags seen: `vegetarian, vegan, contains-nuts, contains-dairy`. Categories: `starter, main, dessert` (12 items).
- No time-of-day field on menu items -> daypart menus stay out of scope.
- CustomerOut: `id, name, phone, email, preferences{}, created_at`

## Seeded preferences
- Priya (1): `{"seating": "outdoor", "dietary": ["vegetarian"]}`
- Rahul (2): `{}`
- Anita (3): `{"allergies": ["nuts"]}`

## Errors
- Missing resource: 404 with `{"detail": "..."}` (e.g. `Menu item not found`, `Customer not found`).
- Validation: 422 (FastAPI shape).
- Observed quirks: unknown `exclude_tags` values are ignored (no error); `/availability` does not reject out-of-hours slots (the 12:00-22:30 rule must be enforced on create).
