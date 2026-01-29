# B-0243 — Refund/Return + Idempotent

## Goal
We will implement the payment (full/part)** after order/payment.

- Refund request/delivery status
- Support for Partial Refund (Item Unit)
- Restock** Integration
- All refund operations are tracked by the idempotent** + event

## Background
- Refund is the most populous area in CS/operation.
- “Cancellation/Cancellation/Cancellation Request/Payment” is included.
- Therefore, you need a refund as order/payment** status + event + fieldback**.

## Scope
### 1) Data model (recommended)
- `refund`
  - refund_id (PK)
  - order_id (FK)
  - payment_id (FK, nullable if offline)
  - status: REQUESTED / APPROVED / PROCESSING / REFUNDED / REJECTED / FAILED
  - refund_amount_total
  - reason_code, reason_text
  - idempotency_key (UNIQUE)
  - created_at, updated_at
- `refund_item`
  - refund_item_id (PK)
  - refund_id (FK)
  - order_item_id (FK)
  - sku_id
  - qty_refund
  - amount_refund
- `refund_event`
  - refund_event_id (PK)
  - refund_id
  - event_type: REFUND_REQUESTED / REFUND_APPROVED / PROVIDER_REFUND_REQUESTED / PROVIDER_REFUND_SUCCEEDED / ...
  - payload_json
  - created_at

> Principle: refund “current status”, refund event “won-in/extra”.

### 2 years ) Refund flow (v1 minimum)
- POST `/api/v1/refunds`
  - body: { order_id, items[] (optional), reason, idempotency_key }
  - validate:
    - .status in (PAID, SHIPPED, DELIVERED)
    - item if specified
    - Non-refundable non-refundable non-refundable
  - create refund REQUESTED + refund_event
- POST `/api/v1/refunds/{refundId}/approve` (Admin/ops)
  - status REQUESTED → APPROVED
- POST `/api/v1/refunds/{refundId}/process`
  - APPROVED → PROCESSING
  - (B-0241 Payment Integration) API call (or mock)
  - REFUNDED, FAILED when failed

### 3) Inventory restore (ledger)
- REFUNDED:
  - sku/qty of refund item**inventory RESTOCK** Performing(used of ledger rule of B-0238)
  - When a stock restore fails:
    - REFUNDED REFUNDED
    - ops task + alert

### 4) Order/Payment integration
- Payment Terms:
  - order_event: REFUND_SUCCEEDED
  - order.status:
    - REFUNDED
    - PartIALLY REFUNDED(Optional) or status maintenance + flag
- payment:
  - provider refund id history(bill transaction)

### 5) Idempotency / replay safety
- idempotency key unique
- provider webhook/response is provided event id to dedup(end extension)
- Returns existing refund when requesting a refund

## Non-goals
- Full flow of exchange/rebound logistics (transfer)
- Company

## DoD
- Complete/Partial refund creation/delivery/delivery flow operation
- refund item/refund event
- Restore Stock LEDgers (restock) Accurate for refund completion
- Backhoe refund 0 from the backhoe ashdo
- ops task

## Observability
- metrics:
  - refund_create_total{status}
  - refund_process_total{status}
  - refund_restock_failed_total
  - refund_idempotent_hit_total
- logs:
  - refund_id, order_id, payment_id, idempotency_key, transition, request_id

## Codex Prompt
Implement Refund domain:
- Add refund/refund_item/refund_event with idempotency_key unique.
- Implement create/approve/process endpoints (process uses mock provider for now).
- On refund success, restock inventory via ledger operation and append events.
- Add tests for partial refund constraints, idempotent create, and restock failure -> ops_task path.
