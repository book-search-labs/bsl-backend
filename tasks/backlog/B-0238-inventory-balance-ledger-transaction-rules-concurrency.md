# B-0238 — Inventory: balance/ledger + transaction rules (reserve/release/deduct/restock)

## Goal
Design/Representation of the company’s core**Research and Consistency**

- Single-numeric inventory** Based on LEDger**
- Unbreakable/replaceable/recovery requests
- Restock

## Background
- Payment/Order is based on failure/retention.
- Simple   TBD   is broken from duplicate request/lays.
- So ** (1) idempotency key + (2) LEDger append + (3) need current balance**

## Scope
### 1) Data model (recommended)
- `inventory_balance`
  - sku_id (PK)
  - on_hand_qty
  - reserved_qty
  - Available qty (computed = on hand -included) or column maintenance
  - updated_at
- `inventory_ledger`
  - ledger_id (PK)
  - sku_id
  - event_type: RESERVE / RELEASE / DEDUCT / RESTOCK / ADJUST
  - qty (signed or positive + type)
  - idempotency_key (unique)
  - ref type/ref id (ORDER ID, PAYMENT ID, etc.)
  - created_at

### 2) Transaction rules
- RESERVE(qty):
  - Condition: Available >= qty
  - reserved += qty
  - ledger append (RESERVE)
- RELEASE(qty):
  - Condition:Capacity >= qty (or min clamp policy)
  - reserved -= qty
  - ledger append (RELEASE)
- DEDUCT(qty):
  - Condition:Capacity >= qty
  - reserved -= qty
  - on_hand -= qty
  - ledger append (DEDUCT)
- RESTOCK(qty):
  - on_hand += qty
  - ledger append (RESTOCK)

### 3) Concurrency control (MySQL standard)
- New  TBD  LO   TBD  row lock
- Terms check in the transaction → update → LEDger insert
- LEDger inserts   TBD  

### 4) API (internal or public)
- GET   TBD   (balance view)
- POST `/api/v1/inventory/{skuId}/reserve`
- POST `/api/v1/inventory/{skuId}/release`
- POST `/api/v1/inventory/{skuId}/deduct`
- POST `/api/v1/inventory/{skuId}/restock`
  Request includes:
- qty
- idempotency_key
- ref_type/ref_id

### 5) Failure handling
- idempotency
- RETURN INSUFFICIENT STOCK
- Part success ban: balance update/ledger insert atomized in same tx

## Non-goals
- Complete integration with your order status notification (=B-0240) and on the following ticket
- Dispersion/Multi DB (v1 single MySQL transaction)

## DoD
- Table/Pharmaceutical Conditions/Transmission Rules are implemented
- Simultaneous reserve 100 tests 0
- idempotency redundancy in Ashdo 0
- Can track events with ledger

## Observability
- metrics:
  - inventory_reserve_total{status}
  - inventory_deduct_total{status}
  - inventory_idempotent_hit_total
- logs:
  - sku_id, qty, idempotency_key, ref_id, before/after

## Codex Prompt
Implement inventory with balance + ledger:
- Use MySQL row locking (SELECT FOR UPDATE) and append-only ledger with unique idempotency_key.
- Provided reserve/release/deduct/restock operations and balance inquiries.
- Add concurrency tests and idempotency retry tests.
- Document transaction rules and error codes.
