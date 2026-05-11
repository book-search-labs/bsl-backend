# B-0803 — Commerce Domain Services Idempotent Internal APIs

## Priority
- P0

## Dependencies
- B-0801
- B-0802

## Goal
order/payment/inventory/shipment 서비스를 실제 DB 기반 internal write service로 만든다.

각 서비스는 자기 DB와 자기 테이블만 소유한다. 모든 write API는 `Idempotency-Key` header를 필수로 받고, 같은 key 재호출 시 동일 결과를 반환한다.

이 internal API들은 checkout-orchestrator/refund-service가 HTTP orchestration으로 호출하는 대상이다. Kafka/outbox command handler가 아니며, core write 성공/실패 판정은 각 서비스의 local DB 상태와 idempotency record를 기준으로 한다.

orchestrator는 global transaction을 제공하지 않는다. 각 서비스는 자기 domain invariant와 side effect를 방어하는 local transaction을 반드시 가져야 한다.

## Scope
### 1) Common idempotency model
- 각 하위 서비스에 `idempotency_record` 추가
  - `id`, `idempotency_key`, `operation_type`, `status`
  - `request_hash`
  - `response_payload`, `error_message`
  - `created_at`, `updated_at`
- unique `idempotency_key`
- status:
  - `PENDING`
  - `PROCESSING`
  - `SUCCEEDED`
  - `UNKNOWN`
  - `FAILED`
  - `CANCELLED`

Idempotency rules:
- 모든 write API는 `Idempotency-Key` header 없으면 `400` 반환
- key format은 orchestrator 기준 `checkout:{checkoutId}:{operation}` 또는 `checkout:{checkoutId}:{operation}:compensate`
- 같은 key + 같은 operation 재호출은 저장된 response 반환
- 같은 key + 다른 operation 재사용은 `409 IDEMPOTENCY_KEY_REUSED` 반환
- 같은 key + 같은 operation이지만 request hash가 다르면 `409 IDEMPOTENCY_PAYLOAD_MISMATCH` 반환
- `PROCESSING` record 재호출은 1차에서 `409 IDEMPOTENCY_IN_PROGRESS` 또는 저장된 최신 상태 반환 중 하나로 통일하고 테스트로 고정
- 외부 호출 timeout 또는 side effect 결과 불명확 상태는 `UNKNOWN`으로 저장하고 status 조회/reconciliation으로 복구해야 함
- 실패 응답을 저장할지 여부를 operation별로 명시하되, domain side effect가 발생한 뒤 실패한 경우는 반드시 response 복구 가능해야 함

Required local transaction defense:
- idempotency record create/check and domain side effect state change must be atomic inside the owning service where possible
- shared finite resources use row lock or atomic conditional update, never read-check-later-write
- inventory reserve must prevent oversell with guarded SQL or optimistic locking
- payment authorization must prevent duplicate authorization for the same idempotency key and must be ready for wallet/balance conditional update if balance payment is introduced
- external side effect adapters must write a pending operation before external call, mark `SUCCEEDED`, `FAILED`, or `UNKNOWN` after the call, and expose lookup by idempotency/client request id
- compensation/release/cancel APIs must be idempotent and must not reuse forward operation idempotency keys

Required idempotency test matrix:
- missing `Idempotency-Key` -> `400`
- first call with a new key creates exactly one domain row and one idempotency row
- duplicate call with the same key and same operation returns byte-for-byte equivalent business response
- duplicate call with the same key does not create extra order/payment/reservation/shipment/cancellation rows
- same key reused for a different operation -> `409 IDEMPOTENCY_KEY_REUSED`
- same key and operation with a different request payload -> `409 IDEMPOTENCY_PAYLOAD_MISMATCH`
- `PROCESSING` duplicate behavior is deterministic and documented
- side effect succeeded but response failed/timeout is recoverable by re-calling the same key
- timeout/unknown side effect is persisted as `UNKNOWN` and can be reconciled
- compensation keys ending with `:compensate` are independent from forward operation keys

### 2) order-service
- Tables:
  - `orders`
  - `order_lines`
- APIs:
  - `POST /internal/orders`
  - `GET /internal/orders/{orderId}`
- Creates order with status `PENDING`
- Stores checkout id, user id, total amount, and item lines
- Request minimum fields: `checkout_id`, `user_id`, `items`, `total_amount`, `currency`
- Response minimum fields: `order_id`, `status`, `total_amount`, `currency`

### 3) payment-service
- Tables:
  - `payment_authorization`
  - `payment_cancellation`
- APIs:
  - `POST /internal/payments/authorize`
  - `POST /internal/payments/cancel`
  - `GET /internal/payments/by-idempotency-key/{idempotencyKey}`
- Mock authorization returns `paymentId` and `pgTransactionId`
- Authorization local transaction must create/replay idempotency and payment authorization state without duplicate PG authorization.
- If payment method later consumes wallet/balance, available/reserved balance must be changed by guarded update or row lock inside payment/wallet owning service.
- External PG timeout must not be marked as permanent failure until idempotency lookup/status reconciliation is attempted.
- Authorize request minimum fields: `checkout_id`, `order_id`, `amount`, `currency`, `method`
- Authorize response minimum fields: `payment_id`, `status`, `pg_transaction_id`, `amount`, `currency`
- Cancel request minimum fields: `checkout_id`, `payment_id`, `reason`
- Cancel response minimum fields: `cancellation_id`, `payment_id`, `status`

### 4) inventory-service
- Tables:
  - `book_stock`
  - `inventory_reservation`
  - `inventory_reservation_line`
- APIs:
  - `POST /internal/inventory/reserve`
  - `POST /internal/inventory/release`
  - `GET /internal/inventory/reservations/by-idempotency-key/{idempotencyKey}`
- Reserve must fail cleanly on insufficient stock
- Use optimistic update or guarded SQL update to prevent over-reservation
- Reserve local transaction must atomically check/update `book_stock` and create `inventory_reservation`.
- Concurrent reservations for the same `book_id` must never make available stock negative.
- Reserve request minimum fields: `checkout_id`, `order_id`, `items`
- Reserve response minimum fields: `reservation_id`, `status`, `items`
- Release request minimum fields: `checkout_id`, `reservation_id`, `reason`
- Release response minimum fields: `reservation_id`, `status`

### 5) shipment-service
- Table:
  - `shipment_request`
- APIs:
  - `POST /internal/shipments`
  - `POST /internal/shipments/cancel`
  - `GET /internal/shipments/by-idempotency-key/{idempotencyKey}`
- Mock shipment request returns `shipmentId`
- Shipment request must be tracked as an idempotent operation. If a real carrier API accepts a shipment irreversibly, classify it as pivot/retriable and use status reconciliation on timeout.
- Create request minimum fields: `checkout_id`, `order_id`, `shipping_address`, `items`
- Create response minimum fields: `shipment_id`, `status`
- Cancel request minimum fields: `checkout_id`, `shipment_id`, `reason`
- Cancel response minimum fields: `shipment_id`, `status`

## Non-goals
- checkout-orchestrator worker
- failure mode
- automatic retry
- cancel/compensation orchestration
- Kafka/outbox command consumer

## Test / Validation
- Each write API requires `Idempotency-Key`
- Same idempotency key returns same response without duplicate domain rows
- Same idempotency key reused for a different operation returns conflict
- In-progress idempotency behavior is tested and documented
- Each service has an explicit idempotency replay test for its write APIs
- Domain row count assertions prove duplicate calls do not create duplicate side effects
- Compensation write APIs use separate `:compensate` keys and are idempotent
- Concurrent same-user or same-book requests prove owning services prevent overspend/oversell through local transactions
- UNKNOWN/reconciliation behavior is tested for external-style payment/shipment operations
- order create/get
- payment authorize/cancel idempotency
- inventory reserve/release and insufficient stock
- shipment create/cancel idempotency
- `./scripts/test.sh`

## DoD
- All four domain services persist their own data
- No service writes another service's tables
- Duplicate write requests are idempotent
- Responses contain enough ids for checkout-orchestrator context payload
- Internal write APIs are usable as HTTP orchestration targets without Kafka/outbox dependency

## Codex Prompt
Implement Commerce MSA phase 3:
- Add DB migrations and repositories for order, payment, inventory, and shipment services.
- Add idempotency_record to each service.
- Implement internal write/read APIs with required `Idempotency-Key` header.
- Enforce key reuse conflict and duplicate response replay.
- Enforce request_hash mismatch conflict and UNKNOWN/reconciliation behavior for uncertain side effects.
- Add local transaction defenses for inventory over-reservation and payment duplicate authorization.
- Add the full idempotency test matrix from this ticket, including duplicate row-count assertions.
- Use the minimum request/response fields from this ticket.
- Keep these services as HTTP orchestration targets; do not add Kafka/outbox command consumers.
- Do not implement failure mode or checkout saga worker yet.
