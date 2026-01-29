# B-0239 — Cart API (cart/cart_item) + concurrency & price snapshot

## Goal
사용자가 상품을 담고 수량을 조정할 수 있는 **장바구니 API**를 구현한다.

- 사용자 기준 cart 1개(활성 카트)
- cart_item 추가/수정/삭제
- **가격 스냅샷** 정책(offer 변경에도 cart가 안정적으로 동작)
- 동시성/중복 요청/수량 제한

## Background
- cart는 “주문 직전 상태”이며, 가격/재고 변동이 잦다.
- 그래서 장바구니엔 **스냅샷**이 필요하고,
  checkout에서 다시 current_offer를 검증/재계산해야 한다.

## Scope
### 1) Data model (recommended)
- `cart`
  - cart_id (PK)
  - user_id (UNIQUE 활성 카트)
  - status: ACTIVE / CHECKED_OUT / ABANDONED
  - created_at, updated_at
- `cart_item`
  - cart_item_id (PK)
  - cart_id (FK)
  - sku_id
  - qty
  - price_snapshot_json (offer_id, price, currency, captured_at)
  - constraints:
    - UNIQUE(cart_id, sku_id) (같은 sku는 한 줄)
  - created_at, updated_at

### 2) Price snapshot policy (v1)
- add/update 시점에 `current_offer`를 조회(B-0237)
- cart_item에 `offer_id`, `unit_price`, `captured_at` 저장
- checkout 시:
  - current_offer 재조회
  - 가격 변동 시 “사용자에게 변경 고지” + 재승인 필요(UX는 U 티켓)

### 3) API
- GET `/api/v1/cart` (active cart 조회/생성)
- POST `/api/v1/cart/items`
  - body: { sku_id, qty, idempotency_key? }
- PATCH `/api/v1/cart/items/{cartItemId}`
  - body: { qty }
- DELETE `/api/v1/cart/items/{cartItemId}`
- DELETE `/api/v1/cart/items` (비우기 optional)

### 4) Validation
- qty: 1..MAX_QTY_PER_ITEM (예: 20)
- MAX_DISTINCT_ITEMS (예: 200)
- 상품 비활성/offer 없음 → add 불가
- 동시 update:
  - optimistic locking(version) 또는 row lock 선택 (v1: row lock 권장)

### 5) Concurrency & idempotency
- add는 `UNIQUE(cart_id, sku_id)`로 upsert 패턴 지원
- idempotency_key(optional):
  - 네트워크 재시도로 중복 add 방지
  - (v1) 없어도 unique로 어느 정도 방지 가능
- cart 업데이트는 동일 tx로 처리

## Non-goals
- 재고 reserve는 checkout/order에서(=B-0240/B-0238 연동)
- 쿠폰/프로모션(추후)
- 멀티 셀러 복잡도(추후)

## DoD
- active cart 생성/조회/추가/수정/삭제 동작
- add 시 current_offer 스냅샷 저장됨
- offer 변경 시 checkout 단계에서 재검증할 수 있도록 정보가 충분함
- 동시 add/update 시 중복/깨짐 없이 안정 동작

## Observability
- metrics:
  - cart_create_total, cart_add_total, cart_update_total, cart_remove_total
  - cart_item_conflict_total
- logs:
  - user_id, cart_id, sku_id, qty, offer_id, request_id

## Codex Prompt
Implement Cart API:
- Create cart/cart_item tables with unique (cart_id, sku_id).
- Add endpoints for get active cart, add/update/remove items.
- On add/update, fetch current_offer and store price snapshot in cart_item.
- Enforce qty and item count limits; handle concurrency safely.
- Add tests for upsert behavior and price snapshot correctness.
