# A-0109 — Product Ops UI (Seller/Offer/Inventory)

## Goal
**Products/Sellers/Operes/Prices/Registration** Admin UI.

## Scope
### 1) Seller Management
- seller list/detail
- Status (active/active), Identity Information (optional), Memo

### 2) SKU / Catalog Ops
- SKU list/detail
- Basic Information (Jet/ISBN Connection/Category etc.), Sales Status

### 3) Offer / Pricing
- Offers
  - price, currency, valid_from/to, shipping_policy
- current offer(currently applicable)

### 4) Inventory (Ledger-based)
- Inventory balance view
- Ledger Events Inquiry (reserve/release/deduct/restock)
- Manual adjustment (required)

## Non-goals
- Payment/Debit(A-0110), Shipping(A-0111)

## API (BFF)
- `GET /admin/sellers`
- `GET /admin/skus`
- `POST /admin/offers`
- `GET /admin/inventory/balance?sku_id=...`
- `GET /admin/inventory/ledger?sku_id=...`

## DoD
- sku/offer CRUD
- inventory inquiry + LEDger details can be checked
- The risk work (replacement manually) left to audit log

## Codex Prompt
Implement the Seller/SKU/Offer/Inventory operation UI in Admin.
Provides a list/detail/reality/modified form and LEDger view screen, and call BFF API only.
