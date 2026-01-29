# B-0237 — Catalog Commerce APIs: SKU / Offer / current_offer

## Goal
The product catalog commerce API** is based on the search/top/order flow.

- SKU(Sales Unit) / Offer(Sales Condition) / Current offer(Currently Applied Price/Policy) View
- User Web details/baskets/checkout “Price snapshots” can be reliably received
- The API works consistently (price/time/delivery policy)

## Background
- If you don’t want to finish your book, you need “there’s”.
- The price/offer varies, so you need a layer that calculates/checks the "current valid value" separated by **current offer**.

## Scope
### Domain & tables (v1.1)
- `sku`
  - sales unit connected with material id
  - Status: ACTIVE/INACTIVE, Seller(seller id) Factory Tour
- `offer`
  - Terms of Sale for sku (Price/time/delivery policy/retention policy)
  - Valid from/valid to
  - ACTIVE/PAUSED/ENDED
- `current_offer` (computed view or query)
  - now returns one of the most priority offer based on
  - Sorting rules (e.g.):
    1) valid window
    2) status=ACTIVE
    3) high
    4) Created at

> Implementation Method: (A) SQL on-the-fly calculation (v1 recommended) / (B) materialized current offer table(add)

### 2 years Public API (BFF)
- GET `/api/v1/skus?materialId=...`
- GET `/api/v1/skus/{skuId}`
- GET `/api/v1/skus/{skuId}/offers`
- GET `/api/v1/skus/{skuId}/current-offer`
- (Optional) GET   TBD   (Detailed)

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
    - is in stock (B-0238 is available)

### 4) Validation / edge cases
- no active offer → 404 or   TBD   current offer (Policy Fixed)
- deterministic with respect rule
- timezones → Save/Reverse to UTC, API returns ISO8601

## Non-goals
- Inventory / Reservation(=B-0238)
- Cart(=B-0239)
- Payment/Order(=B-0240+)

## DoD
- Implement the API above and current offer available based on materialId
- Offer selection rules are documented and fixed with testing
- (when possible) book detail response can hold current offer

## Observability
- metrics: current_offer_lookup_total, current_offer_not_found_total, offer_overlap_detected_total
- logs: sku_id/material_id, selected_offer_id, rule/priority, request_id

## Codex Prompt
Implement Catalog Commerce APIs:
- Add SKU/Offer read endpoints and current_offer selection logic (deterministic priority + time window).
- Return stable response schemas for sku/offer/current_offer.
- Add tests for overlap, inactive offers, time-window boundaries.
- Ensure UTC handling and clear not-found behavior.
