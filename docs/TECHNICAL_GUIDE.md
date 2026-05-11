# Technical Guide

This guide is the reading map for the repository. SSOT order remains:

1. `contracts/`
2. `data-model/` and `db/`
3. `infra/opensearch/`
4. `docs/`

## Service Map

| Service | Port | Notes |
|---|---:|---|
| `web-admin` | 5173 | admin UI |
| `web-user` | 5174 | user UI |
| `bff-service` | 8088 | public API entrypoint |
| `query-service` | 8001 | query prepare/enhance/chat |
| `search-service` | 18087 | search retrieval |
| `autocomplete-service` | 8081 | autocomplete |
| `ranking-service` | 8082 | rank/rerank orchestration |
| `model-inference-service` | 8005 | model scoring |
| `llm-gateway` | 8010 | external LLM gateway |
| `index-writer-service` | 8090 | canonical to search index |
| `checkout-orchestrator-service` | 8091 | Commerce checkout saga |
| `order-service` | 8092 | Commerce order |
| `payment-service` | 8093 | Commerce payment |
| `inventory-service` | 8094 | Commerce inventory |
| `outbox-relay-service` | 8095 | outbox to Kafka relay |
| `olap-loader-service` | 8096 | analytics loader |
| `shipment-service` | 8097 | Commerce shipment |
| `refund-service` | 8098 | Commerce refund request/approve/process |

## Commerce MSA Reading Order

1. `docs/COMMERCE_MSA_API_MAP.md`
2. `docs/COMMERCE_MSA_SAGA.md`
3. `docs/API_SURFACE.md`
4. `docs/ARCHITECTURE.md`

## Commerce MSA Local Dev

```bash
./scripts/local_up.sh
./gradlew :services:checkout-orchestrator-service:bootRun
./gradlew :services:order-service:bootRun
./gradlew :services:payment-service:bootRun
./gradlew :services:inventory-service:bootRun
./gradlew :services:shipment-service:bootRun
./gradlew :services:refund-service:bootRun
./gradlew :services:bff-service:bootRun
./scripts/commerce_msa_smoke.sh
RUN_CHECKOUT_SMOKE=1 ./scripts/commerce_msa_smoke.sh
RUN_FAILURE_SMOKE=1 ./scripts/commerce_msa_smoke.sh
```

`local_up.sh` creates service-local MySQL databases and applies MVP schemas unless `ENABLE_COMMERCE_MSA_DB=0` is set. `pg-simulator` is disabled by default and uses `18092` when enabled with `ENABLE_PG_SIMULATOR=1`.

`RUN_CHECKOUT_SMOKE=1` runs a normal checkout through BFF and verifies duplicate `checkout_key` idempotency. `RUN_FAILURE_SMOKE=1` additionally verifies payment `FAIL_500` manual retry and `SUCCESS_BUT_TIMEOUT` idempotent recovery.

Web Admin exposes checkout saga operations at:

```text
/ops/commerce/checkouts
```

The page calls BFF `/admin/checkouts/**` for list/detail, failed step retry, UNKNOWN reconciliation, and checkout cancellation.

## Checkout Write Flow

Core checkout uses HTTP orchestration:

```text
Web -> BFF -> checkout-orchestrator -> order/inventory/payment/shipment
```

The checkout worker owns ordering and recovery. Each downstream service owns its local invariants and idempotency.

Kafka/outbox is reserved for follow-up work:

```text
settlement, notification, analytics, dashboard projection, replay, audit
```

It is not the checkout command path.

## Transaction Rules

| Rule | Reason |
|---|---|
| No cross-service `@Transactional` | there is no global DB transaction |
| No HTTP call inside DB transaction | avoids lock duration and partial external side effects |
| Use `Idempotency-Key` on every downstream write | duplicate retry must replay |
| Treat timeout as `UNKNOWN` | side effect may already have happened |
| Use compensation only with explicit cancel/recovery path | rollback is a business action, not a DB undo |

## Commerce MSA Observability

Checkout-orchestrator exposes the core recovery counters through `/actuator/prometheus`:

```text
checkout_saga_started_total
checkout_saga_completed_total
checkout_saga_failed_total{step,reason}
checkout_saga_unknown_total{step,reason}
checkout_saga_reconciliation_total{step,result}
checkout_saga_manual_review_total{step,reason}
checkout_saga_pivot_manual_review_total{step,reason}
checkout_compensation_total{step,result}
```

## Tests

Run:

```bash
./gradlew test
./scripts/test.sh
```

Commerce MSA tests cover:

| Area | Test intent |
|---|---|
| duplicate `checkout_key` | one saga returned |
| step idempotency key | persisted key equals downstream header |
| retry | same forward key reused |
| timeout | step becomes `UNKNOWN` before reconciliation |
| compensation | reverse order and `:compensate` keys |
| domain idempotency | duplicate writes do not create duplicate rows |
| inventory local invariant | guarded stock update prevents oversell |
