# U-0119 — Web User: Customization/Shipping UI

## Goal
You can check the status of your order (deposit/delivery/delivery) and tracking your shipment.

## Why
- “Where is my order now?”
- If your order/delivery status is clear, please contact us.

## Scope
### 1) Order History
- Period filter (last 1/3/6 months), status filter (optional)
- Order card: Order number, order date, total amount, status (batch), 1~2 representative items
- 1 stack of paper and paper rolls

### 2) Custom details
- LANGUAGE : 한국어 LANGUAGE : English
- Item List: Product Information/Quantity/Price/Total
- Payment information: payment method/receiver/receiver link(optional)
- Order Status Timeline:
  - CREATED → PAID → READY → SHIPPED → DELIVERED
  - Displaying timestamp per condition

### 3) Tracking
- LOGIN JOIN ORDER MY PAGE
- External tracking URL link (optional)
- Shipping Event Timeline

### 4) Action (Consumer Exposure)
- Before shipping: “Cancel” (linked with U-0120)
- Shipping: “Refund/Refundable Application” (Extra Extension)

## Non-goals
- A complex flow such as returning booking/exchange (return ticket)

## DoD
- Order List/Details/Delivery Inquiry Completed with UX
- Status timeline matches server status
- error/bin status(No order) Completed processing

## Interfaces
- `GET /orders?cursor=...`
- `GET /orders/{order_id}`
- New  TBD   or   TBD  
- New  TBD   (Option)

## Files (example)
- `web-user/src/pages/orders/OrderListPage.tsx`
- `web-user/src/pages/orders/OrderDetailPage.tsx`
- `web-user/src/components/orders/OrderStatusTimeline.tsx`
- `web-user/src/api/orders.ts`

## Codex Prompt
Implement Order history UI:
- List and detail pages with status timeline and tracking section.
- Conditional actions (cancel/refund entry points).
- Handle empty/error states and pagination.
