# BSL Architecture (v3) — Production-ready Blueprint

> This document is the **single source of truth** for BSL’s system shape:
> services, sync/async call paths, transaction boundaries, and ops loops.
>
> **Current state:** Web(User/Admin) → **Query Service direct-call** (legacy)
>
> **Target state:** Web(User/Admin) → **API Gateway** → **BFF** → (QS/SR/AC/Commerce)  
> Internal services are not internet-facing.

---

## 1) Design principles (the rules we don’t break)

1. **Single entrypoint for clients:** all client traffic goes through **Gateway + BFF**.
2. **Read path is stateless & degradable:** search/autocomplete/chat can **degrade** (quality ↓) but must **respond**.
3. **Write path is transactional per service:** each write is atomic **inside one DB**. Cross-service consistency is via **outbox + events + sagas**.
4. **Contracts are versioned:** OpenAPI/JSON Schema **compat gates** in CI.
5. **Observability is built-in:** request_id + trace_id propagate end-to-end; every stage has latency budgets.

---

## 2) System map (logical)

```mermaid
flowchart LR
  subgraph Clients
    UWeb["Web User"]
    AWeb["Web Admin"]
    Mobile["Mobile"]
  end

  subgraph Edge
    GW["API Gateway<br/>Auth / RateLimit / TLS"]
    BFF["BFF (Search API)<br/>fan-out + response assembly<br/>outbox write"]
  end

  subgraph Online["Online Serving"]
    QS["Query Service<br/>normalize/detect<br/>2-pass enhance (conditional)"]
    SR["Search Service<br/>retrieve + hybrid fusion<br/>rerank orchestration"]
    AC["Autocomplete Service<br/>Redis hot + OS miss"]
    IDXW["Index Writer Service<br/>canonical -> search docs<br/>reindex + alias swap"]
    COMLEG["Commerce Legacy API<br/>cart/catalog/home/my/support"]
    CO["Checkout Orchestrator<br/>HTTP saga state machine"]
    ORD["Order Service"]
    PAY["Payment Service"]
    INV["Inventory Service"]
    SHIP["Shipment Service"]
    REF["Refund Service"]
    RS["Ranking Service<br/>feature assembly + scoring orchestrator"]
    MIS["Model Inference Service<br/>cross-encoder / LTR scorer"]
    LLMGW["LLM Gateway<br/>keys/quotas/retries/audit"]
  end

  subgraph Stores["Data Stores"]
    DB[(MySQL)]
    OS[(OpenSearch)]
    R[(Redis)]
    FEAT[(Feature KV / Feature Store)]
    OLAP[(ClickHouse/BigQuery)]
  end

  subgraph Stream["Streaming"]
    OUTBOX[(outbox_event)]
    RELAY["Outbox Relay"]
    K[(Kafka)]
    OLAPL["OLAP Loader"]
  end

  UWeb --> GW --> BFF
  AWeb --> GW --> BFF
  Mobile --> GW --> BFF

  BFF -->|/search| QS --> SR --> OS
  SR --> RS --> MIS
  RS --> FEAT
  BFF -->|/autocomplete| AC --> R
  AC --> OS
  BFF -->|/books/:id| DB

  BFF -->|/chat| QS
  QS --> SR
  QS --> LLMGW

  BFF -->|/cart, catalog, my...| COMLEG --> DB
  BFF -->|/v1/checkout| CO --> DB
  CO -->|HTTP + Idempotency-Key| ORD --> DB
  CO -->|HTTP + Idempotency-Key| INV --> DB
  CO -->|HTTP + Idempotency-Key| PAY --> DB
  CO -->|HTTP + Idempotency-Key| SHIP --> DB
  BFF -->|refund APIs| REF --> DB
  IDXW --> DB
  IDXW --> OS

  BFF --> OUTBOX
  COMLEG --> OUTBOX
  CO --> OUTBOX
  REF -. planned .-> OUTBOX
  AC -. planned .-> OUTBOX
  SR -. planned .-> OUTBOX
  OUTBOX --> RELAY --> K
  K --> OLAPL --> OLAP
  K --> FEAT
```

---

## 3) “Fan-out” means what?

**Fan-out = one request triggers multiple downstream calls** in parallel/sequence, then the caller **assembles** one response.

Example: **BFF /search**
- calls **QS (prepare)** to normalize/detect
- calls **SR (search)** to retrieve & rerank
- optionally calls **DB (detail enrichment)** or policy endpoints
- returns one unified payload to the client

Fan-out must be guarded by:
- per-downstream **timeout budgets**
- **circuit breakers** (degrade mode)
- **idempotency** for side effects (outbox)

Current implementation note:
- **Event emit ownership is primarily in BFF** (search/autocomplete click/impression paths).
- AC/SR direct outbox emit remains a planned hardening path and is not the default production path yet.

---

## 4) Service responsibilities (clear boundaries)

### 4.1 API Gateway (GW)
- TLS termination, routing
- user/admin auth, rate limiting
- forwards trace headers (W3C trace context)

### 4.2 BFF (Search API)
- **single client entrypoint**
- issues `request_id`, propagates `trace_id`
- **fan-out orchestration** + response assembly
- writes domain events to **outbox_event** (search impressions, ac selects, etc.)
- enforces contracts and policy selection (feature flags/experiments)

### 4.3 Query Service (QS) — deterministic 1-pass + conditional 2-pass
- `prepare`: normalize/detect/canonicalKey
- `enhance`: spell(T5)/rewrite/understanding (+ optional RAG hints) **only when gated**
- caching: normalize cache, enhance cache (optional)
- emits debug fields (why enhanced / what strategy)

### 4.4 Search Service (SR) — online search orchestrator (Hybrid included)
- doc BM25 retrieval (`books_doc_v*`)
- optional vector retrieval (`books_vec_v*` or chunks) + **Fusion (RRF)**
- calls RS/MIS to rerank (topN→topK), but must **degrade safely**
- debug/explain output for Admin playground
- emits impression/click/dwell events (via outbox)

### 4.5 Autocomplete Service (AC)
- Redis hot-prefix cache (p99 defense)
- OS prefix query fallback (miss)
- current production event emit is handled by BFF (`/autocomplete/select`); AC-native emit is optional/planned

### 4.6 Ranking Service (RS)
- assembles feature vectors (query-doc, ctr/popularity, freshness, commerce signals)
- calls MIS for scoring (cross-encoder / LTR)
- returns scored results + debug bundle (feature snapshots, model version, reason codes)

### 4.7 Model Inference Service (MIS)
- stateless inference endpoints with:
  - concurrency limits, timeouts, warmup
  - optional dynamic batching
  - model version routing (active/canary) driven by model_registry
- hosts: cross-encoder reranker, LTR scorer (e.g., LambdaMART→ONNX)

### 4.8 Commerce
Commerce is split only for the core write workflow that is useful for MSA learning:
- `checkout-orchestrator-service`: owns checkout saga state, step status, retry, compensation trigger.
- `order-service`: owns order creation/read model.
- `payment-service`: owns mock payment authorization/cancel side effects.
- `inventory-service`: owns stock and reservation invariants.
- `shipment-service`: owns mock shipment request/cancel side effects.
- `refund-service`: owns refund request/approval/process state and orchestrates payment cancel plus optional inventory release.
- legacy `commerce-service`: keeps cart, catalog commerce reads, home panels/benefits/preorders, my page, support, settlement/admin surfaces until separately migrated.

Core checkout writes use **HTTP orchestration**, not Kafka command orchestration. Each service protects its own DB invariants with local transactions and idempotency records.

### 4.9 LLM Gateway (LLMGW)
- centralized place to call external LLM providers
- key/quotas/retries, audit logs, prompt templates, cost controls

### 4.10 Outbox Relay Service
- reads pending `outbox_event` rows and publishes them to Kafka
- enforces idempotent publish (`dedup_key`) and replay-safe retry semantics
- isolates transport failures from online read/write paths

### 4.11 Index Writer Service
- owns canonical-to-search document projection (`material*` -> `books_doc_*`)
- executes reindex jobs with checkpointing and alias cutover (`books_doc_read/write`)
- supports blue/green index rollout without direct client impact

### 4.12 OLAP Loader Service
- consumes analytics/event streams (Kafka) and materializes OLAP tables
- normalizes event schema versions and backfills replay windows
- powers dashboard/reporting pipelines without coupling to online APIs

---

## 5) Synchronous call flows (who calls whom)

### 5.1 Search (happy path)
```mermaid
sequenceDiagram
  autonumber
  participant C as Client(U/A)
  participant B as BFF
  participant Q as QS
  participant S as SR
  participant O as OpenSearch
  participant R as RS
  participant M as MIS
  participant D as MySQL

  C->>B: POST /v1/search
  B->>Q: POST /query/prepare
  Q-->>B: QueryContext(q_norm, detected, hints)
  B->>S: POST /internal/search(QueryContext + filters)
  S->>O: BM25 retrieve topN
  O-->>S: bm25_docs
  S->>R: POST /internal/rank(topN candidates)
  R->>M: POST /v1/score(batch)
  M-->>R: scores
  R-->>S: ranked docs (+debug)
  S->>D: (optional) enrich/detail snapshot
  D-->>S: details
  S-->>B: SearchResponse
  B-->>C: Response (items + facets + debug? optional)
```

### 5.2 Search (fallback / degrade)
- **vector retrieval fails** → SR returns **BM25-only**
- **MIS/RS timeout** → SR returns **fused order without rerank**
- **0 results / low confidence** → SR calls QS `/enhance`, retries once with `q_final`

### 5.3 Autocomplete
```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant B as BFF
  participant A as AC
  participant R as Redis
  participant O as OpenSearch

  C->>B: GET /v1/autocomplete?q=...
  B->>A: GET /internal/autocomplete?q=...
  A->>R: GET prefix cache
  alt cache hit
    R-->>A: topK
  else cache miss
    A->>O: prefix query (ac_candidates_read)
    O-->>A: candidates
  end
  A-->>B: suggestions
  B-->>C: suggestions
```

### 5.4 Chat (RAG)
- BFF `/chat` → QS `/chat` orchestrates:
  - normalize/rewrite → retrieve chunks via SR/OS → rerank chunks via MIS (optional) → LLMGW generate with citations
- Stream mode: QS relays LLMGW token stream (`meta`/`delta`/`done`), and BFF proxies SSE without token splitting.
- Internal debug path: QS `/internal/rag/explain` exposes lexical/vector/fused/selected traces with rerank/rewrite reason codes.

---

## 6) Transactions, consistency, and “multi-service calls”

### 6.1 Reads (QS/SR/RS/MIS/AC)
These are **query-only** flows:
- no distributed transaction needed
- correctness model: **best-effort + degrade safe**
- guarantees: **bounded latency** and **consistent tracing**

### 6.2 Writes (Commerce/Admin ops)
We do not use 2PC or a cross-service `@Transactional` boundary.

**Rule:** a write is atomic only inside the owning service DB. Cross-service consistency is made from a saga state machine, idempotency, retry, compensation, and manual recovery.

#### Core checkout pattern: HTTP orchestration
1. BFF receives `POST /v1/checkout`.
2. BFF calls checkout-orchestrator `POST /internal/checkouts`.
3. Checkout-orchestrator stores `checkout_saga`, `checkout_saga_step`, and follow-up `outbox_event`.
4. A DB polling worker claims a READY/FAILED/UNKNOWN step with a conditional update.
5. The worker calls order/inventory/payment/shipment over HTTP with the persisted `Idempotency-Key`.
6. The worker stores step response, context, retry/UNKNOWN/manual-review status in short local transactions.

HTTP calls are never executed inside a DB transaction. The flow returns the currently available saga state to the user; it does not wait for Kafka consumers.

#### Follow-up events: Outbox/Kafka
`outbox_event` is still used, but only for follow-up consumers:
- settlement
- notification
- analytics
- dashboard projections
- replay/audit/recovery inspection

It is not the command queue for checkout step execution.

---

## 7) Data, indexing, and ops loops

### 7.1 Raw → Canonical → Index (blue/green)
- Raw ingest: `raw_node(payload_hash, node_id)` for idempotency
- Canonical: upsert into `material/agent/concept/material_*`
- Index build: create `books_doc_v{N}` → validate → alias swap → mark READY/ACTIVE

### 7.2 Synonyms/normalization publishing
- `synonym_set` is versioned in DB
- publishing pipeline updates OS analyzers and triggers safe reindex if required
- rollback = republish previous version

---

## 8) Ranking: LTR + cross-encoder (production pattern)

### 8.1 Why 2-stage is the default
- **LTR (LambdaMART):** cheap, feature-based, explainable (topN)
- **Cross-encoder:** expensive but precise (topK subset)

### 8.2 Offline eval regression gates (CI blocking)
Datasets:
- Golden (fixed) + Shadow (recent) + Hard (typo/chosung/series)

Metrics:
- NDCG@10, MRR@10, Recall@100
- 0-result-rate, latency proxy (rerank call rate, p99 risk)

---

## 9) Commerce MSA note

Current Commerce split is intentionally narrow:
- MSA: checkout/order/payment/inventory/shipment/refund experiment path
- Legacy kept: cart, catalog commerce reads, settlement/admin, customer/my page, support, home merchandising

Recovery model:
- Forward recovery: retry failed or UNKNOWN steps with the same idempotency key until success or manual review.
- Backward recovery: explicit cancel/compensation uses reverse step order and separate `:compensate` idempotency keys.
- Pivot policy: if a step becomes irreversible, it is treated as a pivot; after pivot success, automatic rollback is avoided and forward/manual recovery is preferred.

Detailed runbook: `docs/COMMERCE_MSA_SAGA.md`.

---

## 10) Observability & SRE essentials
- OpenTelemetry tracing, W3C propagation (gateway → bff → internal)
- Metrics: p95/p99, error rate, cache hit rate, Kafka lag
- Logs: JSON structured, PII redaction
- Runbooks: reindex failures, OS snapshot restore, DB restore, Kafka DLQ replay

---

## 11) Local development ports (fixed)
- web-admin: **5173**
- web-user: **5174**
- bff-service: **8088**
- checkout-orchestrator-service: **8091**
- order-service: **8092**
- payment-service: **8093**
- inventory-service: **8094**
- outbox-relay-service: **8095**
- olap-loader-service: **8096**
- shipment-service: **8097**
- refund-service: **8098**
- search-service: **18087**
- autocomplete-service: **8081**
- ranking-service: **8082**
- query-service: **8001**
- model-inference-service: **8005**
- llm-gateway: **8010**
- index-writer-service: **8090**

---

## Appendix — Minimal API surface (target)

### Public (BFF)
- `POST /search` (alias: `/v1/search`)
- `GET /autocomplete` (alias: `/v1/autocomplete`)
- `GET /books/{id}` (alias: `/v1/books/{id}`)
- `POST /chat` (alias: `/v1/chat`)
- `POST /v1/checkout`
- `GET /v1/checkout/{checkoutId}`
- `POST /v1/checkout/{checkoutId}/steps/{stepName}/retry`
- `POST /v1/checkout/{checkoutId}/cancel`
- legacy kept: `POST /v1/cart/*`, `POST /v1/order/*`, `POST /v1/payment/*` ...

### Internal (service-to-service)
- QS: `/query/prepare`, `/query/enhance`, `/chat`, `/internal/rag/explain`
- SR: `/search` (alias: `/internal/search`), `/internal/explain`
- AC: `/autocomplete` (alias: `/internal/autocomplete`)
- RS: `/rerank` (alias: `/internal/rank`)
- MIS: `/v1/score`, `/v1/models`
- Checkout Orchestrator: `/internal/checkouts`, `/internal/checkouts/{id}`, `/internal/checkouts/{id}/steps/{stepName}/retry`, `/internal/checkouts/{id}/cancel`
- Order: `/internal/orders`, `/internal/orders/{orderId}`
- Payment: `/internal/payments/authorize`, `/internal/payments/cancel`, `/internal/payments/by-idempotency-key/{idempotencyKey}`, `/internal/admin/failure-mode`
- Inventory: `/internal/inventory/reserve`, `/internal/inventory/release`, `/internal/inventory/reservations/by-idempotency-key/{idempotencyKey}`, `/internal/admin/failure-mode`
- Shipment: `/internal/shipments`, `/internal/shipments/cancel`, `/internal/shipments/by-idempotency-key/{idempotencyKey}`, `/internal/admin/failure-mode`
