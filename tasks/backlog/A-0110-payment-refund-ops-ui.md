# A-0110 — Payment & Refund Ops UI

## Goal
View/Record UI for payment/refund operation (CS/disability).

## Scope
- Payment list/detail
  - Payment Status (PENDING/APPROVED/FAILED/CANCELED)
  - Failure Oil/PG Response Summary
- Refund list/detail
  - Refund / Refund
  - Displaying the status of LEDger
- CS Note/Tag(Optional)

## Safety / Policy
- REFUND/Cancel RBAC Rights Check + Audit log Record

## API (BFF)
- `GET /admin/payments`
- `GET /admin/payments/{id}`
- `POST /admin/payments/{id}/cancel`
- `GET /admin/refunds`
- `POST /admin/refunds`

## DoD
- Allow operators to figure out the failure cause/status within 1 minute
- Can be processed for partial refund (including voucher/reduction log)

## Codex Prompt
Implement Payment/Refund operation UI in Admin.
We provide payment/refundable lists, tax and refund execution form, and risk action to make sure Modal +audit.
