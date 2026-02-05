# B-0237 — Catalog Commerce APIs: SKU / Offer / current_offer

## Goal
검색/상세/주문 플로우의 기반이 되는 **상품 카탈로그 커머스 API**를 만든다.

- SKU(판매 단위) / Offer(판매 조건) / current_offer(현재 적용 가격/정책) 조회
- User Web 상세/장바구니/체크아웃이 “가격 스냅샷”을 안정적으로 받을 수 있게
- Admin에서 운영(가격/기간/배송정책)을 바꿔도 API가 일관되게 동작

## Background
- 도서 검색만으로 끝나지 않으려면 “살 수 있는 상태”가 필요.
- price/offer는 변동되므로 **current_offer**를 분리해 “현재 유효한 값”을 계산/조회하는 레이어가 필요.

## Scope
### 1) Domain & tables (v1.1 기준)
- `sku`
  - material_id(도서)와 연결되는 판매 단위
  - 상태: ACTIVE/INACTIVE, 판매자(seller_id) 등
- `offer`
  - sku에 대한 판매 조건(가격/기간/배송정책/재고정책)
  - 기간: valid_from/valid_to
  - 상태: ACTIVE/PAUSED/ENDED
- `current_offer` (computed view or query)
  - now 기준으로 가장 우선순위 높은 offer 1개를 반환
  - 정렬 규칙(예시):
    1) valid window 안에 있음
    2) status=ACTIVE
    3) priority 높은 것
    4) 같으면 최신 created_at

> 구현 방식: (A) SQL로 on-the-fly 계산 (v1 권장) / (B) materialized current_offer 테이블(추후)

### 2) Public API (BFF 경유 전제)
- GET `/api/v1/skus?materialId=...`
- GET `/api/v1/skus/{skuId}`
- GET `/api/v1/skus/{skuId}/offers`
- GET `/api/v1/skus/{skuId}/current-offer`
- (옵션) GET `/api/v1/materials/{materialId}/current-offer` (상세화면 편의)

### 3) Response shape (minimum)
- sku:
  - sku_id, material_id, seller_id, status
- offer:
  - offer_id, sku_id, price, currency
  - valid_from, valid_to, status, priority
  - shipping_policy_id (or embedded)
- current_offer:
  - sku + selected offer + computed fields:
    - effective_price
    - is_in_stock (B-0238이 나오기 전엔 placeholder 가능)

### 4) Validation / edge cases
- no active offer → 404 or `null` current_offer (정책 고정)
- overlapping offers → priority rule로 deterministic
- timezones → UTC로 저장/비교, API는 ISO8601 반환

## Non-goals
- 재고 차감/예약(=B-0238)
- 장바구니(=B-0239)
- 결제/주문(=B-0240+)

## DoD
- 위 API를 구현하고, materialId 기반으로 current_offer 조회 가능
- offer 선택 규칙이 문서화되어 있고 테스트로 고정됨
- (가능하면) book detail 응답에 current_offer를 붙일 수 있는 기반 마련(BFF에서 fan-out)

## Observability
- metrics: current_offer_lookup_total, current_offer_not_found_total, offer_overlap_detected_total
- logs: sku_id/material_id, selected_offer_id, rule/priority, request_id

## Codex Prompt
Implement Catalog Commerce APIs:
- Add SKU/Offer read endpoints and current_offer selection logic (deterministic priority + time window).
- Return stable response schemas for sku/offer/current_offer.
- Add tests for overlap, inactive offers, time-window boundaries.
- Ensure UTC handling and clear not-found behavior.
