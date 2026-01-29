# B-0239 — Cart API (cart/cart_item) + concurrency & price snapshot

## Goal
The user implements API**, which can fix the goods and adjust the quantity.

- 1 cart (active cart)
- cart item
- New *Price snapshot** Policy (the cart works stably even when the offer changes)
- Simultaneous/Uniform Request/Capacity Limit

## Background
- cart is “last order status” and the price/replace change is frequent.
- So you need a shopping cart**Snapshot**,
checkout should be validated and reorganized again current offer.

## Scope
### 1) Data model (recommended)
- `cart`
  - cart_id (PK)
  - user id (UNIQUE active cart)
  - status: ACTIVE / CHECKED_OUT / ABANDONED
  - created_at, updated_at
- `cart_item`
  - cart_item_id (PK)
  - cart_id (FK)
  - sku_id
  - qty
  - price_snapshot_json (offer_id, price, currency, captured_at)
  - constraints:
    - UNIQUE(cart id, sku id)
  - created_at, updated_at

### 2) Price snapshot policy (v1)
- add/update at the point   TBD    View(B-0237)
- cart item   TBD  ,   TBD  ,   TBD  
- checkout time:
  - current offer REVIEW
  - When price change “change to user” + need to receive (UX U ticket)

### 3) API
- GET   TBD   (active cart view/reduced)
- POST `/api/v1/cart/items`
  - body: { sku_id, qty, idempotency_key? }
- PATCH `/api/v1/cart/items/{cartItemId}`
  - body: { qty }
- DELETE `/api/v1/cart/items/{cartItemId}`
- DELETE   TBD   (optional)

### 4) Validation
- Qty: 1..MAX QTY PER ITEM (Yes: 20)
- MAX DISTINCT ITEMS
- Product inert/offer no → add indispensable
- Price:
  - optimistic locking(version) or row lock selection (v1: row lock recommended)

### 5) Concurrency & idempotency
- add support upsert pattern with   TBD   
- idempotency_key(optional):
  - Network retry road redundancy add protection
  - (v1) It can be prevented by unique
- cart update to the same tx

## Non-goals
- In stock reserve checkout/order(=B-0240/B-0238 Integration)
- Coupon/Promotion (Extra)
- Multi-Cell Complexity (Extra)

## DoD
- active cart generate/check/add/modified/delete operation
- Save current offer snapshots when add
- If you change the offer, checkout will be enough information to be reissued at the stage.
- Stable operation without duplicate/frequency at simultaneous add/update

## Observability
- metrics:
  - cart_create_total, cart_add_total, cart_update_total, cart_remove_total
  - cart_item_conflict_total
- logs:
  - user_id, cart_id, sku_id, qty, offer_id, request_id

## Codex Prompt
Implement Cart API:
- Create cart/cart_item tables with unique (cart_id, sku_id).
- Add endpoints for get active cart, add/update/remove items.
- On add/update, fetch current_offer and store price snapshot in cart_item.
- Enforce qty and item count limits; handle concurrency safely.
- Add tests for upsert behavior and price snapshot correctness.
