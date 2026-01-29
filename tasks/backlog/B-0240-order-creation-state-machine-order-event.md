# B-0240 — Order creation + Status + order event (Saga-ready)

## Goal
To create a cart → order → make a payment/delivery, the main body of your order is**Order domain**.

- {{if compare at price min > price min > price min > price min}}
- Change the status of state status + event(order event)
- “Saga-ready” structure for integration with payment/delivery

## Background
- The order is based on failure/relay/return call.
- When finishing with single table update, it should not be debugging during operation.
- So **Order status + event log + field key** is required.

## Scope
### 1) Data model (recommended)
- `orders`
  - order_id (PK)
  - user_id
  - status: CREATED / PAYMENT_PENDING / PAID / READY_TO_SHIP / SHIPPED / DELIVERED / CANCELED / REFUND_PENDING / REFUNDED
  - currency, total_amount, shipping_fee, discount_amount (optional)
  - idempotency key (UNIQUE) ← checkout prevention
  - cart_id (optional link)
  - created_at, updated_at
- `order_item`
  - order_item_id (PK)
  - order_id (FK)
  - sku_id, qty
  - price_snapshot_json (offer_id, unit_price, captured_at, title/author optional)
  - item_total_amount
- `order_event`
  - order_event_id (PK)
  - order_id
  - event_type: ORDER_CREATED / INVENTORY_RESERVED / PAYMENT_REQUESTED / PAYMENT_SUCCEEDED / PAYMENT_FAILED / ORDER_CANCELED / ...
  - payload_json
  - created_at

> Principle: “orders are current state”, “order event causes/add”

### 2 years ) Checkout → Order create flow (v1 recommended)
**POST /api/v1/orders**
Request:
- cart id (or items directly)
- shipping_address_id (or address snapshot)
- payment method (v1 can be mocked)
- idempotency_key

Process:
1) cart view + items load
2) Re-called "current offer" for each item(B-0237)** (re-quote)
  - Price Change Policy:
    - (A) Instant Failure (409 PRICE CHANGED) + Front Receipt
    - (B) Progress to new prices + Notice to UI
→ v1 (A) Recommended
3) B-0238 reservation:
  - skuby quantity
  - rollback(409 OUT OF STOCK)
4) order event(ORDER CREATED, INVENTORY RESERVED)
5) (Connect with payment ticket B-0241) payment intent creation or PAYMENT PENDING

### 3 years APIs
- POST `/api/v1/orders` (create)
- GET `/api/v1/orders/{orderId}`
- GET `/api/v1/orders?userId=...` (user order list)
- POST   TBD   (v1: CREATED/PAYMENT PENDING only)
- (optional internal) POST   TBD   (called in payment/shipment)

### 4) State machine (v1 minimum)
- CREATED → PAYMENT_PENDING
- PAYMENT_PENDING → PAID | CANCELED
- PAID → READY_TO_SHIP → SHIPPED → DELIVERED
- (cancel) CREATED/PAYMENT PENDING → CANCELED (inventory RELEASE required)
- (refund) Extended from B-0243 after PAID

### 5) Idempotency
- create request   TBD   unique guarantee
- Returning the same key: Returning the existing order(200)

## Non-goals
- Mod→real from PG(=B-0241)
- Tracking(=B-0242)
- Partial cancellation/refund(=B-0243)

## DoD
- Order create/list/get/cancel implementation
- Price re-quote policy is fixed and guaranteed by testing
- In stock reserve/release integration (with rollback)
- status/original tracking with order event
- idempotency redundancy order 0 from Ashdo

## Observability
- metrics:
  - order_create_total{status}, order_cancel_total{status}
  - order_price_changed_total, order_out_of_stock_total
  - order_idempotent_hit_total
- logs:
  - order_id, user_id, cart_id, idempotency_key, status_transition, request_id

## Codex Prompt
Implement Order domain:
- Add orders/order_item/order_event tables with idempotency_key unique.
- Implement POST /orders with re-quote(current_offer) + inventory reserve + event append.
- Implement get/list/cancel with valid state transitions and inventory release on cancel.
- Add tests for idempotency, price-changed 409, out-of-stock rollback, and event history integrity.
