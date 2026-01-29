# U-0120 — Web User: Cancellation/Refund Request

## Goal
You can apply for cancellation/refund of orders (including refund).

## Why
- Payment/Return/Order Status Key section
- In the UI, you need to clearly show “Available Condition” and reduce the operation.

## Scope
### 1) Cancellationable condition display
- Order Status Based:
  - Prior to delivery (CREATED/PAID/READY): Cancelable
  - After shipping (SHIPPED/DELIVERED): refund/return (according to policy)
- Displays available/paid items (partial cancellation/refundable support)

### 2) Cancellation/Refund application form
- Select Sayu (Dropdown) + Detailed Sayu (Text)
- Refunds (refundable refunds)
- Return: Select item + Select quantity

### 3) Application results/status
- Application Complete screen + In-process status display
- Refund status in order details (REQUESTED/APPROVED/REJECTED/COMPLETED)

### 4) Safety Device UX
- "Delivery in stock/delivery in case of cancellation"
- Prevents duplicate submission (button disable, idempotency key is responsible for server)

## Non-goals
- Automated return repair/exchange process (repair)

## DoD
- Cancellation/refund application is successfully created and reflected on the status screen
- In the impossible condition, the application is blocked and the reason is displayed
- Completed rehabilitation / oil handling

## Interfaces
- `POST /orders/{order_id}/cancel`
- New  TBD  
- `GET /refunds/by-order/{order_id}`

## Files (example)
- `web-user/src/pages/refund/RefundRequestPage.tsx`
- `web-user/src/components/refund/RefundItemSelector.tsx`
- `web-user/src/api/refund.ts`

## Codex Prompt
Implement Cancel/Refund UI:
- Gate by order status, support partial selection, capture reasons.
- Show request status in order detail and handle retries/errors.
