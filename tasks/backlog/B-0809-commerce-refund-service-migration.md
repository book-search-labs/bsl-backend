# B-0809 — Refund Service Migration

## Priority
- P0

## Dependencies
- B-0800
- B-0801
- B-0803
- B-0805

## Goal
기존 refund API와 refund/refund_item/refund_event 책임을 `refund-service`로 분리한다.

checkout compensation에서는 payment cancel이 보상 역할을 하지만, 사용자/관리자 환불 API는 core Commerce MSA 범위에 포함해 `refund-service`로 분리한다.

## API Migration Scope
### Public
- `POST /api/v1/refunds`
- `GET /api/v1/refunds/{refundId}`
- `GET /api/v1/refunds/by-order/{orderId}`

### Admin
- `GET /admin/refunds`
- `GET /admin/refunds/{refundId}`
- `POST /admin/refunds`
- `POST /admin/refunds/{refundId}/approve`
- `POST /admin/refunds/{refundId}/process`

## Data Ownership
- `refund`
- `refund_item`
- `refund_event`
- refund policy snapshot fields if present

Does not own:
- payment authorization rows
- inventory stock rows
- order rows

## Internal APIs
- `POST /internal/refunds`
- `POST /internal/refunds/{refundId}/approve`
- `POST /internal/refunds/{refundId}/process`
- `GET /internal/refunds/by-order/{orderId}`

## Cross-Service Flow
Refund process is a saga-like workflow:
- validate order via `order-service`
- cancel/partial cancel payment via `payment-service`
- release/restock inventory via `inventory-service` when policy requires
- update order refund state via `order-service` internal API or event
- write refund events and outbox events

Communication model:
- refund create/approve/process는 core Commerce MSA 범위이므로 HTTP orchestration으로 처리한다.
- refund-service가 order/payment/inventory를 HTTP로 호출하고, 각 호출은 DB transaction 밖에서 수행한다.
- Kafka/outbox는 refund 진행 command가 아니라 settlement, notification, analytics, dashboard projection, replay, audit 같은 후속 처리를 위한 domain event에 사용한다.
- refund-service는 global transaction을 제공하지 않는다. payment cancel/refund, inventory restock/release, order refund-state update는 각 owning service local transaction과 idempotency로 보호되어야 한다.
- PG refund/cancel이 실제 외부 side effect로 확정되는 경우 해당 step은 pivot으로 보고, 이후 order/inventory 상태 반영 실패는 forward retry/manual recovery 중심으로 처리한다.
- PG timeout은 `UNKNOWN`으로 저장하고 provider/idempotency status reconciliation 후 다음 상태를 결정한다.

## Idempotency
- refund create/process APIs require `Idempotency-Key`
- duplicate process request must not double cancel payment or double restock inventory
- duplicate or concurrent refund process requests must assert payment/inventory/order row counts and external operation counts
- request hash mismatch with the same idempotency key must return conflict

## Events
- `REFUND_REQUESTED`
- `REFUND_APPROVED`
- `REFUND_REJECTED`
- `REFUND_PROCESSING`
- `REFUND_COMPLETED`
- `REFUND_FAILED`

위 이벤트는 후속 처리용이며 refund process 성공/실패 판정은 refund-service DB 상태와 idempotency record가 기준이다.

## Non-goals
- Real PG refund integration beyond existing mock/cancel behavior
- Settlement re-computation implementation; settlement remains on legacy `commerce-service` in this scope

## Test / Validation
- refund request create/get/list
- admin approve/process
- duplicate refund process idempotency
- payment cancel failure leaves refund retryable
- payment cancel/refund timeout leaves refund step `UNKNOWN` and reconciliation can recover it
- pivot success followed by order/inventory update failure uses forward retry/manual review
- inventory restock duplicate prevention
- concurrent duplicate refund process does not double refund or double restock
- BFF routes refund APIs to `refund-service`
- `./scripts/test.sh`

## DoD
- Refund APIs no longer depend on legacy `commerce-service`
- Refund workflow is retryable and idempotent
- Refund workflow is pivot-aware and records UNKNOWN external outcomes before reconciliation
- Refund domain events are emitted to outbox for future settlement, notification, analytics, dashboard, replay, and ledger integration
- Refund core flow is HTTP-orchestrated and does not depend on Kafka/outbox commands

## Codex Prompt
Migrate refund APIs to refund-service:
- Add refund tables, idempotency, public/admin/internal APIs.
- Implement refund processing with payment cancel and inventory restock calls outside DB transactions.
- Add pivot-aware refund processing, UNKNOWN/reconciliation for external payment side effects, and local transaction/invariant tests.
- Keep refund processing HTTP-orchestrated; use outbox only for follow-up domain events.
- Route BFF refund APIs to refund-service.
- Add tests for duplicate process, payment failure, and restock idempotency.
