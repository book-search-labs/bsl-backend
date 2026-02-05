# B-0240 — Order 생성 + 상태머신 + order_event (Saga-ready)

## Goal
장바구니 → 주문 생성 → 결제/배송으로 이어지는 “상거래의 본체”인 **Order 도메인**을 운영형으로 구현한다.

- 주문 생성(Checkout) 시 **가격 스냅샷/재고 예약/멱등성**을 보장
- 상태머신(order_status) + 이벤트(order_event)로 변경 이력을 남김
- 결제/배송과의 연동을 위해 “Saga-ready” 구조(추후 확장 용이)

## Background
- 주문은 실패/재시도/중복 호출이 기본이다.
- 단일 테이블 update로 끝내면 운영 중 디버깅이 안 된다.
- 그래서 **주문 상태 + 이벤트 로그 + 멱등키**가 필수.

## Scope
### 1) Data model (recommended)
- `orders`
  - order_id (PK)
  - user_id
  - status: CREATED / PAYMENT_PENDING / PAID / READY_TO_SHIP / SHIPPED / DELIVERED / CANCELED / REFUND_PENDING / REFUNDED
  - currency, total_amount, shipping_fee, discount_amount (optional)
  - idempotency_key (UNIQUE)  ← checkout 재시도 방지
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

> 원칙: “orders는 현재 상태”, “order_event는 변경 원인/추적”

### 2) Checkout → Order create flow (v1 권장)
**POST /api/v1/orders**
Request:
- cart_id (or items 직접)
- shipping_address_id (or address snapshot)
- payment_method (v1은 mock 가능)
- idempotency_key

Process (single transaction boundary 가능한 범위까지):
1) cart 조회 + items 로드
2) 각 item에 대해 **current_offer 재조회(B-0237)** (re-quote)
  - 가격 변동 시 정책:
    - (A) 즉시 실패(409 PRICE_CHANGED) + 프론트 재승인
    - (B) 새 가격으로 진행 + UI에 고지
      → v1은 (A) 추천
3) 재고 예약(B-0238 RESERVE):
  - sku별 qty reserve
  - reserve 실패 시 전체 rollback(409 OUT_OF_STOCK)
4) orders/order_item 생성 + order_event(ORDER_CREATED, INVENTORY_RESERVED)
5) (결제 티켓 B-0241과 연결) payment intent 생성 or PAYMENT_PENDING으로 전이

### 3) APIs (BFF 경유 전제)
- POST `/api/v1/orders` (create)
- GET `/api/v1/orders/{orderId}`
- GET `/api/v1/orders?userId=...` (user order list)
- POST `/api/v1/orders/{orderId}/cancel` (v1: CREATED/PAYMENT_PENDING에서만)
- (optional internal) POST `/internal/orders/{orderId}/events` (payment/shipment에서 호출)

### 4) State machine (v1 최소)
- CREATED → PAYMENT_PENDING
- PAYMENT_PENDING → PAID | CANCELED
- PAID → READY_TO_SHIP → SHIPPED → DELIVERED
- (cancel) CREATED/PAYMENT_PENDING → CANCELED (inventory RELEASE 필요)
- (refund) PAID 이후는 B-0243에서 확장

### 5) Idempotency
- create 요청은 `idempotency_key` unique로 보장
- 동일 key 재호출 시: 기존 order를 그대로 반환(200)

## Non-goals
- 실결제 PG(=B-0241에서 mock→real)
- 배송 추적(=B-0242)
- 부분취소/부분환불(=B-0243)

## DoD
- Order create/list/get/cancel 구현
- 가격 re-quote 정책이 고정되고 테스트로 보장됨
- 재고 reserve/release 연동이 정확(rollback 포함)
- order_event로 상태/원인 추적 가능
- idempotency 재시도에서 중복 주문 0

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
