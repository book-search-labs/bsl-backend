# B-0242 — Shipment/Tracking (shipment/shipment_item/shipment_event) + carrier status updates

## Goal
We will implement order shipping/delivery tracking in operation.

- From shipment creation (exit preparation) to invoice registration and delivery status update
- Tracking status change to event event
- v1: Mock carrier update/manual update
- v2: Actual courier API polling/webhook expandable structure

## Background
- Shipping is an external system, causing delay/return/purchase problem.
- Before order status, it is linked with a shipment status, and requires a tracking log for CS response.

## Scope
### 1) Data model (recommended)
- `shipment`
  - shipment_id (PK)
  - order_id (FK)
  - status: READY / SHIPPED / IN_TRANSIT / DELIVERED / RETURNED / LOST
  - carrier_code (CJ, LOTTE, UPS ...)
  - tracking_number
  - shipped_at, delivered_at
  - created_at, updated_at
- `shipment_item`
  - shipment_item_id (PK)
  - shipment_id
  - order_item_id
  - sku_id, qty
- `shipment_event`
  - shipment_event_id (PK)
  - shipment_id
  - event_type: SHIPMENT_CREATED / TRACKING_ASSIGNED / STATUS_UPDATED / DELIVERED_CONFIRMED
  - payload_json
  - created_at

### 2) APIs
- POST `/api/v1/shipments` (create)
  - body: { order_id, items[] }
  - validate: order.status=PAID or READY TO SHIP policy
  - create shipment READY + event
- POST `/api/v1/shipments/{shipmentId}/tracking`
  - body: { carrier_code, tracking_number }
  - status: READY → SHIPPED, set shipped_at, event append
  - SHIPPED
- POST `/api/v1/shipments/{shipmentId}/mock/status`
  - body: { status: IN_TRANSIT|DELIVERED }
  - update shipment status + event
  - if DELIVERED: delivered_at set, update order.status=DELIVERED, order_event append

### 3) Carrier integration (v2 extension points)
- Poller job:
  - tracking number lists periodically view
  - If you have a status change, send event append + status before
- Webhook:
  - idempotency(provider event id)

### 4) Idempotency
- (carrier code + tracking number) unique (optional)
- status update event id or (shipment id + status + timestamp) dedup

## Non-goals
- Return/Exchange Full Flow (Extra)
- Multiple shipments/part shipments (extra; v1 can be 1 order = 1 shipment)

## DoD
- Create / Register / Status Update Operation
- shipment event Customizable
- Send your inquiry directly to us
- DELIVERED Scenario E2E possible with mock status

## Observability
- metrics:
  - shipment_create_total{status}, shipment_tracking_assign_total{status}
  - shipment_status_update_total{from,to}
- logs:
  - shipment_id, order_id, carrier_code, tracking_number, transition, request_id

## Codex Prompt
Implement Shipment/Tracking:
- Add shipment/shipment_item/shipment_event tables.
- Implement create shipment, assign tracking, and mock status update endpoints.
- Append shipment_event for every change and transition order status accordingly.
- Add tests for valid transitions and delivered flow.
- Leave extension hooks for carrier polling/webhook.
