# B-0242 — Shipment/Tracking (shipment/shipment_item/shipment_event) + carrier status updates

## Goal
주문 출고/배송 추적을 운영형으로 구현한다.

- shipment 생성(출고 준비)부터 송장(tracking) 등록, 배송 상태 업데이트까지
- 이벤트(shipment_event)로 상태 변경 추적
- v1: Mock carrier 업데이트/수동 업데이트
- v2: 실제 택배사 API 폴링/웹훅 확장 가능 구조

## Background
- 배송은 외부 시스템이므로 지연/중복/순서 문제 발생.
- 주문 상태 전이는 shipment 상태와 연동되며, CS 대응을 위해 추적 로그가 필요.

## Scope
### 1) Data model (recommended)
- `shipment`
  - shipment_id (PK)
  - order_id (FK)
  - status: READY / SHIPPED / IN_TRANSIT / DELIVERED / RETURNED / LOST
  - carrier_code (CJ, LOTTE, UPS ...)
  - tracking_number
  - shipped_at, delivered_at
  - created_at, updated_at
- `shipment_item`
  - shipment_item_id (PK)
  - shipment_id
  - order_item_id
  - sku_id, qty
- `shipment_event`
  - shipment_event_id (PK)
  - shipment_id
  - event_type: SHIPMENT_CREATED / TRACKING_ASSIGNED / STATUS_UPDATED / DELIVERED_CONFIRMED
  - payload_json
  - created_at

### 2) APIs
- POST `/api/v1/shipments` (create)
  - body: { order_id, items[] }
  - validate: order.status=PAID or READY_TO_SHIP 정책
  - create shipment READY + event
- POST `/api/v1/shipments/{shipmentId}/tracking`
  - body: { carrier_code, tracking_number }
  - status: READY → SHIPPED, set shipped_at, event append
  - also update order.status = SHIPPED or READY_TO_SHIP → SHIPPED (정책 고정)
- POST `/api/v1/shipments/{shipmentId}/mock/status`
  - body: { status: IN_TRANSIT|DELIVERED }
  - update shipment status + event
  - if DELIVERED: delivered_at set, update order.status=DELIVERED, order_event append

### 3) Carrier integration (v2 extension points)
- Poller job:
  - tracking_number 목록을 주기적으로 조회
  - 상태 변화가 있으면 shipment_event append + 상태 전이
- Webhook:
  - carrier webhook 수신, 서명 검증, idempotency(provider_event_id)

### 4) Idempotency
- tracking 등록은 (carrier_code + tracking_number) unique (optional)
- status update는 provider_event_id 또는 (shipment_id + status + timestamp) dedup

## Non-goals
- 반품/교환 전체 플로우(추후)
- 다중 shipment/부분 배송(추후; v1은 1 order = 1 shipment 가정 가능)

## DoD
- shipment 생성/송장 등록/상태 업데이트 동작
- shipment_event로 추적 가능
- order 상태 전이가 shipment와 일관되게 동작
- mock status로 DELIVERED 시나리오 E2E 가능

## Observability
- metrics:
  - shipment_create_total{status}, shipment_tracking_assign_total{status}
  - shipment_status_update_total{from,to}
- logs:
  - shipment_id, order_id, carrier_code, tracking_number, transition, request_id

## Codex Prompt
Implement Shipment/Tracking:
- Add shipment/shipment_item/shipment_event tables.
- Implement create shipment, assign tracking, and mock status update endpoints.
- Append shipment_event for every change and transition order status accordingly.
- Add tests for valid transitions and delivered flow.
- Leave extension hooks for carrier polling/webhook.
