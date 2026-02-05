# B-0243 — Refund/부분환불 + 재고복원(ledger) 플로우 (Idempotent)

## Goal
주문/결제 이후 발생하는 **환불(전체/부분)**을 운영형으로 구현한다.

- 환불 요청/승인/완료 상태머신
- 부분환불(아이템 단위) 지원
- 환불 시 **재고 ledger 복원(restock)** 연동
- 모든 환불 동작은 **멱등(idempotent)** + 이벤트로 추적 가능

## Background
- 환불은 CS/운영에서 가장 많이 터지는 영역이다.
- “결제 취소/부분 취소/중복 요청/지연”이 기본.
- 따라서 refund도 order/payment처럼 **상태 + 이벤트 + 멱등키**가 필요.

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

> 원칙: refund는 “현재 상태”, refund_event는 “원인/추적”.

### 2) Refund flow (v1 최소)
- POST `/api/v1/refunds`
  - body: { order_id, items[] (optional), reason, idempotency_key }
  - validate:
    - order.status in (PAID, SHIPPED, DELIVERED) 등 정책
    - items 지정 없으면 전체환불
    - 이미 refunded qty 초과 환불 금지
  - create refund REQUESTED + refund_event
- POST `/api/v1/refunds/{refundId}/approve` (Admin/ops)
  - status REQUESTED → APPROVED
- POST `/api/v1/refunds/{refundId}/process`
  - APPROVED → PROCESSING
  - (B-0241 Payment 연동) provider refund API 호출(또는 mock)
  - 성공 시 REFUNDED, 실패 시 FAILED

### 3) Inventory restore (ledger)
- 환불 완료(REFUNDED) 시:
  - refund_item의 sku/qty로 **inventory RESTOCK** 수행(B-0238의 ledger 규칙 사용)
  - 재고 복원 실패 시:
    - refund는 REFUNDED 유지(결제는 이미 취소됨)
    - 대신 ops_task 생성(수동 처리) + alert

### 4) Order/Payment integration
- refund 완료 시:
  - order_event: REFUND_SUCCEEDED
  - order.status:
    - 전체환불이면 REFUNDED
    - 부분환불이면 PARTIALLY_REFUNDED(선택) or 상태 유지 + flag
- payment:
  - provider_refund_id 기록(결제사 트랜잭션)

### 5) Idempotency / replay safety
- refund create는 idempotency_key unique
- provider webhook/response는 provider_event_id로 dedup(향후 확장)
- 동일 환불 요청 재시도 시 기존 refund 반환

## Non-goals
- 교환/반품 물류(반송) 전체 플로우
- 정산/회계

## DoD
- 전체/부분 환불 생성/승인/처리/완료 플로우 동작
- refund/refund_item/refund_event 저장
- 환불 완료 시 재고 ledger 복원(restock) 정확
- 멱등키 재시도에서 중복 환불 0
- 장애 시 ops_task로 수동처리 루트 존재

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
