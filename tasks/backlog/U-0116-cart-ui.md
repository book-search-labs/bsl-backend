# U-0116 — Web User: Shopping Cart UI/UX (Cart)

## Goal
You can customize your product to your shopping cart.

## Why
- Starting point of commerce flow
- Price/Rego Snapshot Policy and operating issues are often encountered → you should clearly show in UI

## Scope
### 1) Shopping cart list screen
- Item List: Cover/Item/Capacity/Price/Total
- Change quantity(+/-) and input directly
- Delete(Item Unit), Full Rain

### 2) Price/Resident warning display
- “Price changed” badge
- "Safety / Goods" badge + quantity automatic adjustment guide

### 3) Total/Payment button
- {$*img src thumb figure}
- CTA: “Checkout”

### 4) Empty state
- Empty cart guide + popular/recommended (optional) or searched

## Non-goals
- Coupons / Points / Promotions

## DoD
- Copyright (c) 2015 SHINSEGAE. All Rights Reserved.
- {{if compare at price min > price min}}
- Go to Checkout

## Interfaces
- `GET /cart`
- `POST /cart/items`
- `PATCH /cart/items/{id}`
- `DELETE /cart/items/{id}`

## Files (example)
- `web-user/src/pages/cart/CartPage.tsx`
- `web-user/src/components/cart/CartItemRow.tsx`
- `web-user/src/api/cart.ts`

## Codex Prompt
Build Cart UI:
- Implement Cart page with list, quantity updates, remove, clear.
- Show price/stock change warnings.
- Add summary panel and proceed-to-checkout CTA.
