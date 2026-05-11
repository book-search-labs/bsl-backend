# Commerce MSA API Map

This document fixes the Commerce split boundary for the MSA experiment.

## MSA Scope

These domains move out of legacy `commerce-service`:

| Domain | Service | Port | Owner responsibility |
|---|---:|---:|---|
| Checkout workflow | `checkout-orchestrator-service` | 8091 | Saga state, step ordering, retry, compensation trigger |
| Order | `order-service` | 8092 | Order create/read |
| Payment | `payment-service` | 8093 | Mock authorization/cancel, idempotency, failure mode |
| Inventory | `inventory-service` | 8094 | Stock, reservation/release, oversell prevention |
| Shipment | `shipment-service` | 8097 | Mock shipment request/cancel, idempotency, failure mode |
| Refund | `refund-service` | 8098 | Refund request/approve/process, payment cancel orchestration, inventory release |

## Legacy-Kept Scope

These remain in `commerce-service` until a separate ticket explicitly migrates them:

| Area | Examples |
|---|---|
| Cart | `/api/v1/cart`, cart item CRUD |
| Catalog commerce reads | SKUs, offers, material current offer |
| Home merchandising | panels, collections, benefits, preorders |
| Customer/my page | wishlist, comments, wallet, notifications, gifts, inquiries |
| Support | support tickets and events |
| Settlement/admin | settlement, admin payment/shipment/inventory views |

## Public BFF Routes

External clients call only BFF.

| Route | Target | Notes |
|---|---|---|
| `POST /v1/checkout` | checkout-orchestrator `POST /internal/checkouts` | Starts saga and returns current state |
| `GET /v1/checkout/{checkoutId}` | checkout-orchestrator `GET /internal/checkouts/{checkoutId}` | Reads saga/steps/context |
| `POST /v1/checkout/{checkoutId}/steps/{stepName}/retry` | checkout-orchestrator retry API | Requires `reason`, `operator_id` |
| `POST /v1/checkout/{checkoutId}/steps/{stepName}/reconcile` | checkout-orchestrator reconcile API | Schedules UNKNOWN reconciliation |
| `POST /v1/checkout/{checkoutId}/cancel` | checkout-orchestrator cancel API | Runs backward compensation |
| `POST /api/v1/refunds` | refund-service `POST /api/v1/refunds` | Requires `Idempotency-Key` |
| `GET /api/v1/refunds/{refundId}` | refund-service `GET /api/v1/refunds/{refundId}` | Reads refund state |
| `GET /api/v1/refunds/by-order/{orderId}` | refund-service `GET /api/v1/refunds/by-order/{orderId}` | Reads refunds for an order |

## Contracts

Commerce MSA payload contracts:

| Payload | Schema | Example |
|---|---|---|
| checkout start request | `contracts/commerce-checkout-start-request.schema.json` | `contracts/examples/commerce-checkout-start-request.sample.json` |
| checkout action request | `contracts/commerce-checkout-action-request.schema.json` | `contracts/examples/commerce-checkout-action-request.sample.json` |
| checkout response | `contracts/commerce-checkout-response.schema.json` | `contracts/examples/commerce-checkout-response.sample.json` |
| checkout list response | `contracts/commerce-checkout-list-response.schema.json` | `contracts/examples/commerce-checkout-list-response.sample.json` |
| checkout action response | `contracts/commerce-checkout-action-response.schema.json` | `contracts/examples/commerce-checkout-action-response.sample.json` |
| refund create request | `contracts/commerce-refund-create-request.schema.json` | `contracts/examples/commerce-refund-create-request.sample.json` |
| refund response | `contracts/commerce-refund-response.schema.json` | `contracts/examples/commerce-refund-response.sample.json` |
| refund list response | `contracts/commerce-refund-list-response.schema.json` | `contracts/examples/commerce-refund-list-response.sample.json` |

## Internal Routes

| Service | Route | Idempotency |
|---|---|---|
| checkout-orchestrator | `POST /internal/checkouts` | `checkout_key` unique |
| checkout-orchestrator | `GET /internal/checkouts?status=&limit=` | admin list |
| checkout-orchestrator | `GET /internal/checkouts/{checkoutId}` | read |
| checkout-orchestrator | `POST /internal/checkouts/{checkoutId}/steps/{stepName}/retry` | reuses original step key |
| checkout-orchestrator | `POST /internal/checkouts/{checkoutId}/steps/{stepName}/reconcile` | reuses original step key |
| checkout-orchestrator | `POST /internal/checkouts/{checkoutId}/cancel` | compensation keys |
| order-service | `POST /internal/orders` | `Idempotency-Key` required |
| order-service | `GET /internal/orders/{orderId}` | read |
| payment-service | `POST /internal/payments/authorize` | `Idempotency-Key` required |
| payment-service | `POST /internal/payments/cancel` | `Idempotency-Key` required |
| payment-service | `GET /internal/payments/by-idempotency-key/{idempotencyKey}` | reconciliation |
| inventory-service | `POST /internal/inventory/reserve` | `Idempotency-Key` required |
| inventory-service | `POST /internal/inventory/release` | `Idempotency-Key` required |
| inventory-service | `GET /internal/inventory/reservations/by-idempotency-key/{idempotencyKey}` | reconciliation |
| shipment-service | `POST /internal/shipments` | `Idempotency-Key` required |
| shipment-service | `POST /internal/shipments/cancel` | `Idempotency-Key` required |
| shipment-service | `GET /internal/shipments/by-idempotency-key/{idempotencyKey}` | reconciliation |
| refund-service | `POST /internal/refunds` | `Idempotency-Key` required |
| refund-service | `POST /internal/refunds/{refundId}/approve` | `Idempotency-Key` required |
| refund-service | `POST /internal/refunds/{refundId}/process` | `Idempotency-Key` required |
| refund-service | `GET /internal/refunds/{refundId}` | read |
| refund-service | `GET /internal/refunds/by-order/{orderId}` | read |

## Communication Model

Core checkout is synchronous HTTP orchestration:

`BFF -> checkout-orchestrator -> order/inventory/payment/shipment`

Kafka/outbox is not the checkout command path. `outbox_event` is for settlement, notification, analytics, dashboard projection, replay, and audit follow-up consumers.

Refund create/approve/process is also synchronous HTTP orchestration. `refund-service` calls `payment-service` cancel and optional `inventory-service` release with service-specific idempotency keys. Refund outbox events are only for follow-up consumers.

## Idempotency Keys

Forward step keys:

| Step | Key |
|---|---|
| `CREATE_ORDER` | `checkout:{checkoutId}:CREATE_ORDER` |
| `RESERVE_STOCK` | `checkout:{checkoutId}:RESERVE_STOCK` |
| `AUTHORIZE_PAYMENT` | `checkout:{checkoutId}:AUTHORIZE_PAYMENT` |
| `REQUEST_SHIPMENT` | `checkout:{checkoutId}:REQUEST_SHIPMENT` |

Compensation keys:

| Compensation | Key |
|---|---|
| shipment cancel | `checkout:{checkoutId}:REQUEST_SHIPMENT:compensate` |
| payment cancel | `checkout:{checkoutId}:AUTHORIZE_PAYMENT:compensate` |
| inventory release | `checkout:{checkoutId}:RESERVE_STOCK:compensate` |

Refund keys:

| Flow | Key |
|---|---|
| create refund | caller-provided `Idempotency-Key` |
| approve refund | caller-provided `Idempotency-Key` |
| process refund | caller-provided `Idempotency-Key` |
| payment cancel side effect | `refund:{refundId}:PAYMENT_CANCEL` |
| inventory release side effect | `refund:{refundId}:INVENTORY_RELEASE` |
