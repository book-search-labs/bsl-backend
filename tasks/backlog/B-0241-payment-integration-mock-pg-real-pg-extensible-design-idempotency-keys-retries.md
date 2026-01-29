# B-0241 — Payment Integration (Mock PG → Real PG Extension Design) + idempotency + retry/webhook

## Goal
Make your order payment flow as “operated”

- V1: News News Mock PG**
- v2: Expandable structure with Real PG (webhook/remote check/reset/background)
- PAYMENT PENDING → PAID/FAILED/CANCELED

## Background
- Payments are external systems, so there is a lot of duplicates/paintings/backgrounds.
- So, you need to have **payment self-consuming + event + fieldback**.

## Scope
### 1) Data model (recommended)
- `payment`
  - payment_id (PK)
  - order_id (FK)
  - status: INITIATED / AUTHORIZED / CAPTURED / FAILED / CANCELED
  - amount, currency
  - provider: MOCK / KCP / TOSS / STRIPE ...
  - provider payment id (external payment key)
  - idempotency key
  - created_at, updated_at
- `payment_event`
  - payment_event_id (PK)
  - payment_id
  - event_type: PAYMENT_INITIATED / PROVIDER_CONFIRMED / CAPTURE_SUCCEEDED / CAPTURE_FAILED / WEBHOOK_RECEIVED ...
  - payload_json
  - created_at

### 2) Payment flow (v1: Mock)
- POST `/api/v1/payments` (create payment intent)
  - body: { order_id, amount, idempotency_key }
  - validate: order.status=PAYMENT_PENDING, amount matches order total
  - create payment INITIATED + event
- POST `/api/v1/payments/{paymentId}/mock/complete`
  - body: { result: SUCCESS|FAIL }
  - SUCCESS: payment CAPTURED, emit event, update order to PAID (via internal call or domain service)
  - FAIL: payment FAILED, update order stays PAYMENT_PENDING or moves to CANCELED based on policy

### 3) Webhook-ready design (v2)
- POST `/api/v1/payments/webhook/{provider}`
  - Signature verification (linked with the following I-0311/Security ticket)
  - idempotency: provider event id unique processing
  - out-of-order processing:
    - CAPTURE can be prescribed prior to the transition
    - No-op

### 4) Order integration
- Payment success:
  - order_event: PAYMENT_SUCCEEDED
  - orders.status = PAID
- Payment Failure (FAILED/CANCELED):
  - order_event: PAYMENT_FAILED or PAYMENT_CANCELED
  - (Policy) Automatic cancel + release available after a certain time (Add ops/cron)

### 5) Retry / idempotency
- payment create protection with idempotency key
- webhooks event id
- If the internal condition is “processed”, it will endlessly

## Non-goals
- Partial cancellation/refund(=B-0243)
- Calculation/Tax invoice etc.

## DoD
- Mock PG enables successful and shield scenario reproduction
- payment/payment event is left and order status before/Event is accurate
- Duplicate payment / duplicate webhook processing with idempotency 0
- Configuration Points Documented

## Observability
- metrics:
  - payment_create_total{status}, payment_capture_total{status}
  - payment_webhook_total{provider,status}
  - payment_idempotent_hit_total
- logs:
  - order_id, payment_id, provider_payment_id, idempotency_key, transition, request_id

## Codex Prompt
Implement Payment domain:
- Add payment/payment_event tables with idempotency_key unique.
- Implement create payment intent and a mock complete endpoint to simulate success/failure.
- On success/failure, append events and transition order status accordingly.
- Add webhook-ready handler skeleton with signature verification placeholder and provider_event_id idempotency.
- Add tests for retries and duplicate webhook handling.
