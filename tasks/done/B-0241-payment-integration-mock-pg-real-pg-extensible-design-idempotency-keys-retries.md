# B-0241 — Payment 연동 (Mock PG → Real PG 확장 설계) + idempotency + retry/webhook

## Goal
주문 결제 플로우를 “운영형”으로 만든다.

- v1: **Mock PG**로 결제 성공/실패/취소를 재현 가능
- v2: Real PG로 확장 가능한 구조(웹훅/서명검증/재시도/멱등)
- 결제 이벤트로 Order 상태 전이(PAYMENT_PENDING → PAID/FAILED/CANCELED)

## Background
- 결제는 외부 시스템이므로 중복/지연/순서뒤바뀜이 흔함.
- 따라서 **payment 자체도 상태머신 + 이벤트 + 멱등키**가 필요.

## Scope
### 1) Data model (recommended)
- `payment`
  - payment_id (PK)
  - order_id (FK)
  - status: INITIATED / AUTHORIZED / CAPTURED / FAILED / CANCELED
  - amount, currency
  - provider: MOCK / KCP / TOSS / STRIPE ...
  - provider_payment_id (외부 결제키)
  - idempotency_key (UNIQUE)  ← 결제시도 중복 방지
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
  - signature 검증(추후 I-0311/보안 티켓과 연동)
  - idempotency: provider_event_id unique 처리
  - out-of-order 처리:
    - CAPTURE 먼저 와도 상태 전이 가능
    - 이미 완료된 결제는 no-op

### 4) Order integration
- 결제 성공(CAPTURED) 시:
  - order_event: PAYMENT_SUCCEEDED
  - orders.status = PAID
- 결제 실패(FAILED/CANCELED) 시:
  - order_event: PAYMENT_FAILED or PAYMENT_CANCELED
  - (정책) 일정 시간 후 자동 cancel + inventory release 가능(추후 ops/cron)

### 5) Retry / idempotency
- payment create는 idempotency_key로 보호
- webhook은 provider_event_id로 보호
- 내부 상태 전이는 “이미 처리됨”이면 무해하게 종료

## Non-goals
- 부분취소/부분환불(=B-0243)
- 정산/세금계산서 등

## DoD
- Mock PG로 성공/실패 시나리오 재현 가능
- payment/payment_event가 남고 order 상태 전이/이벤트가 정확
- idempotency로 중복 결제/중복 웹훅 처리 0
- provider 확장 포인트가 문서화됨

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
