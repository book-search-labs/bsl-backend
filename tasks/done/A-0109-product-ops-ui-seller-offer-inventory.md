# A-0109 — Product Ops UI (Seller/Offer/Inventory)

## Goal
커머스 운영을 위한 **상품/판매자/오퍼/가격/재고** 관리 UI.

## Scope
### 1) Seller Management
- seller list/detail
- 상태(활성/비활성), 정산 정보(선택), 메모

### 2) SKU / Catalog Ops
- SKU list/detail
- 기본 정보(제목/ISBN 연결/카테고리 등), 판매 상태

### 3) Offer / Pricing
- Offer 생성/수정
  - price, currency, valid_from/to, shipping_policy
- current_offer 조회(현재 적용 오퍼)

### 4) Inventory (Ledger 기반)
- Inventory balance 조회
- Ledger 이벤트 조회(reserve/release/deduct/restock)
- 수동 조정(권한 필요)

## Non-goals
- 결제/환불(A-0110), 배송(A-0111)

## API (BFF)
- `GET /admin/sellers`
- `GET /admin/skus`
- `POST /admin/offers`
- `GET /admin/inventory/balance?sku_id=...`
- `GET /admin/inventory/ledger?sku_id=...`

## DoD
- seller/sku/offer CRUD 가능
- 재고 조회 + ledger 내역 확인 가능
- 위험 작업(재고 수동조정)은 audit_log에 남음

## Codex Prompt
Admin에서 Seller/SKU/Offer/Inventory 운영 UI를 구현하라.
리스트/상세/생성·수정 폼과 ledger 조회 화면을 제공하고, BFF API만 호출하도록 하라.
