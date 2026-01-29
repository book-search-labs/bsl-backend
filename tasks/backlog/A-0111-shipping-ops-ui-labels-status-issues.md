# A-0111 — Shipping Ops UI (labels/status/issues)

## Goal
UI for shipping operations (export/transportation/status/ensurement).

## Scope
- Shipment list/detail
  - READY/SHIPPED/DELIVERED/EXCEPTION
- Registration of label/transportation (optional: CSV upload or single entry)
- Skip to content
  - Lost/Related/Report Status Record + Memo

## API (BFF)
- `GET /admin/shipments`
- `GET /admin/shipments/{id}`
- `POST /admin/shipments/{id}/label`
- `POST /admin/shipments/{id}/status`

## DoD
- Order the operator→Export→Check the tracking status on the screen
- Registration / status update is possible (recommended / notification)

## Codex Prompt
Shipping to Admin Implement Ops UI.
We provide a list of shipments/registration/registration/registration/registration/registration/registration/registration/registration/registration/registration/registration log integration.
