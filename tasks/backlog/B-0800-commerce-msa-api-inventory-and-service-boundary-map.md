# B-0800 — Core Commerce MSA API Inventory + Service Boundary Map

## Priority
- P0

## Dependencies
- Existing Commerce Service baseline
- `docs/API_SURFACE.md`
- `services/commerce-service/src/main/java/com/bsl/commerce/api/**`

## Goal
기존 `commerce-service` 중 checkout/order/payment/inventory/shipment/refund API만 MSA 전환 대상으로 확정하고, API별 target service와 BFF routing strategy를 문서/테스트 가능한 migration map으로 고정한다.

이 티켓은 구현 전에 경계를 먼저 고정하는 작업이다. cart/catalog/settlement/customer/merchandising/support는 1차 MSA 대상이 아니며, 기존 `commerce-service`에 남긴다.

## Target Service Map
Core Commerce write path를 아래 서비스들로 분리한다.

- `checkout-orchestrator-service`: checkout saga, retry, cancel, compensation
- `order-service`: orders/order_lines/order status read model
- `payment-service`: payment authorization/cancel/webhook/mock PG integration
- `inventory-service`: stock, reservation, inventory ledger/admin adjustment
- `shipment-service`: shipment request/status/label/tracking
- `refund-service`: refund request/approval/process, refund item/event, refund compensation coordination with payment/inventory/order

## Communication Model
- Core checkout flow는 HTTP orchestration으로 처리한다.
- BFF는 checkout-orchestrator를 HTTP로 호출하고, checkout-orchestrator는 order/payment/inventory/shipment를 HTTP로 호출한다.
- 사용자 응답은 Kafka consumer 완료를 기다리지 않고, 즉시 가능한 checkout 결과를 반환한다.
- 즉시 가능한 결과는 최소 `checkout_id`, `status`, `current_step`, step 상태이며, downstream 지연/timeout이 있으면 `PROCESSING` 또는 `FAILED_RETRYING` 같은 현재 상태를 반환한다.
- Kafka/outbox는 checkout 진행을 위한 command queue가 아니다.
- Kafka/outbox는 정산, 알림, analytics, dashboard projection, replay, audit 같은 후속 처리에 사용한다.
- migrated API의 event ownership은 후속 처리 이벤트 소유권을 뜻하며, core write path의 동기 호출 책임을 대체하지 않는다.

## Consistency and Recovery Model
- Core Commerce MSA는 global transaction 또는 distributed transaction을 구현하지 않는다.
- 업무 정합성은 saga state machine, 각 서비스의 local transaction, idempotency, retry, compensation, reconciliation, manual recovery의 조합으로 만든다.
- checkout-orchestrator는 workflow 순서, partial state, step status, retry, compensation trigger만 책임진다.
- order/payment/inventory/shipment/refund는 자기 데이터와 자기 side effect의 invariant를 local transaction으로 방어한다.
- 같은 user의 서로 다른 checkout 동시 실행을 orchestrator local transaction만으로 전역 차단한다고 가정하지 않는다.
- 잔액, 결제 authorization, 재고, 배송 접수, 환불 같은 한정 자원/외부 side effect는 owning service가 row lock, conditional update, unique key, operation table로 방어한다.
- timeout은 즉시 실패가 아니라 `UNKNOWN` 또는 retryable unknown outcome으로 기록하고, idempotency 조회/status reconciliation으로 복구한다.
- 각 workflow step은 `COMPENSATABLE`, `PIVOT`, `RETRIABLE` 중 하나로 분류되어야 한다.
- pivot 이후 실패는 기본적으로 rollback이 아니라 forward recovery/manual recovery로 처리한다.
- pivot 이후 compensation이 필요하면 기술적 rollback이 아니라 reversal/cancellation 같은 별도 업무 transaction으로 설계한다.

## Existing API Migration Inventory
### Public user APIs
- `/api/v1/checkout*` -> `checkout-orchestrator-service`
- `/api/v1/orders*` -> `order-service` for reads/cancel entry, orchestrator for checkout write
- `/api/v1/payments*` -> `payment-service`
- `/api/v1/refunds*` -> `refund-service`
- `/api/v1/shipments*` -> `shipment-service`

### Admin APIs
- `/admin/inventory*` -> `inventory-service`
- `/admin/payments*` -> `payment-service`
- `/admin/refunds*` -> `refund-service`
- `/admin/shipments*` -> `shipment-service`
- checkout saga ops -> `checkout-orchestrator-service`

### Explicit Non-Migrated APIs
아래 API는 이번 MSA 전환 범위에서 제외하고 legacy `commerce-service`에 유지한다.

- `/api/v1/cart*`
- `/api/v1/skus*`
- `/api/v1/materials/*/current-offer`
- `/api/v1/addresses*`
- `/api/v1/my/**`
- `/api/v1/home/**`
- `/api/v1/support/tickets*`
- `/admin/sellers*`
- `/admin/skus*`
- `/admin/offers*`
- `/admin/settlements*`
- `/admin/support/tickets*`

## Scope
### 1) Migration map artifact
- Add `docs/COMMERCE_MSA_API_MAP.md`
- Include every current Commerce controller endpoint and mark it as `MIGRATE_CORE_MSA` or `KEEP_LEGACY_COMMERCE`
- Mark owner service, public/internal route, required idempotency behavior, HTTP orchestration responsibility, and follow-up event ownership for migrated APIs
- Mark resource owner, local invariant, step category (`COMPENSATABLE|PIVOT|RETRIABLE`), and recovery policy for migrated write APIs

### 2) BFF routing matrix
- Define BFF downstream config keys for core MSA services only
- Decide which public/admin routes move in which ticket
- Keep external clients behind BFF only

### 3) Decommission policy
- Existing `commerce-service` remains as the owner of non-core Commerce APIs
- Legacy Commerce is not decommissioned in this migration
- New checkout/order/payment/inventory/shipment/refund work targets the new services after this map lands

## Non-goals
- Implement new services
- Modify contracts
- Remove legacy Commerce

## Test / Validation
- Script or lightweight test verifies all current Commerce controller mappings are represented in `COMMERCE_MSA_API_MAP.md` as either migrated or legacy-kept
- BFF route migration checklist exists
- `./scripts/test.sh`

## DoD
- No existing Commerce API is unassigned
- Core MSA target service ownership is explicit
- Core checkout communication model is explicitly HTTP orchestration, not Kafka command orchestration
- Global transaction is explicitly rejected and replaced by saga state + local transaction defense + recovery policy
- Each migrated write API has an owning service, protected invariant, side-effect type, and recovery policy
- Kafka/outbox follow-up use cases are limited to settlement, notification, analytics, dashboard, replay, and audit-style processing
- Non-core Commerce APIs are explicitly left on legacy `commerce-service`
- checkout/order/payment/inventory/shipment/refund migration can proceed ticket-by-ticket without guessing boundaries

## Codex Prompt
Create the core Commerce MSA API inventory:
- Scan current `commerce-service` controllers.
- Add `docs/COMMERCE_MSA_API_MAP.md` mapping every endpoint as core-MSA migrated or legacy-kept.
- Define BFF route migration order, service ownership, idempotency expectations, and legacy coexistence policy.
- Document that core checkout uses HTTP orchestration for immediate available results.
- Document that Kafka/outbox is for settlement, notification, analytics, dashboard, replay, and audit follow-up processing only.
- Document the consistency model: no global transaction, local transaction defense per owning service, step category, pivot boundary, UNKNOWN/reconciliation, and recovery policy.
- Migrate only checkout/order/payment/inventory/shipment/refund APIs.
- Do not implement services yet.
