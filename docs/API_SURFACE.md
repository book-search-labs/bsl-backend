# API Surface (Service Endpoint Catalog)

This document defines the **public API surface** of the Book Search project.
It is intentionally concise, implementation-agnostic, and **must not contradict SSOT**.

---

## SSOT Order (Source of Truth)

1. `contracts/` — inter-service and public payload schemas + examples (**highest priority**)
2. `data-model/` + `db/` — catalog/source data model and persistence
3. `infra/opensearch/` — derived search index mappings/analyzers
4. `docs/` — rationale/runbooks (must not conflict with SSOT)

---

## Global Conventions

### Base URLs (Local Dev Defaults)

- BFF (Search API): `http://localhost:8088`
- Query Service (QS): `http://localhost:8001`
- Search Service (SS): `http://localhost:8002`
- Autocomplete Service (ACS): `http://localhost:8003`
- Ranking Service (RS): `http://localhost:8004`
- Model Inference Service (MIS): `http://localhost:8005`

> Ports are defaults for local development. Production deployment may differ.

### Common Headers

- `x-trace-id` (optional): if present, services should propagate it downstream
- `x-request-id` (optional): if present, services should propagate it downstream
- If not provided, services generate them and include them in structured responses where applicable.

### Common Fields (Structured Responses)

All structured responses that follow `contracts/*` must include:

- `version`
- `trace_id`
- `request_id`

### Error Responses

- MVP: services may return a minimal error shape:
  ```json
  { "error": { "code": "string", "message": "string" }, "trace_id": "string", "request_id": "string" }
  ```
- If `contracts/error.schema.json` exists, services **must** return that shape.

### Content Types

- Requests: `Content-Type: application/json`
- Responses: `application/json; charset=utf-8`

### Status Codes (MVP)

- `200 OK` — success
- `400 Bad Request` — invalid input
- `404 Not Found` — unknown route
- `500 Internal Server Error` — unexpected error (avoid leaking internals)

---

# 1) BFF (Search API)

**Responsibility**: single client entrypoint for search + autocomplete + book detail.

## GET `/health`
**Purpose**: liveness probe  
**Response**: `200 OK`
```json
{ "status": "ok", "trace_id": "string", "request_id": "string" }
```

## GET `/ready`
**Purpose**: readiness probe (downstream connectivity)  
**Response**: `200 OK`
```json
{
  "status": "ok|degraded",
  "trace_id": "string",
  "request_id": "string",
  "downstream": {
    "query_service": "ok|error",
    "search_service": "ok|error",
    "autocomplete_service": "ok|error"
  }
}
```

## POST `/search`
**Purpose**: fan-out to QS → SS and return SearchResponse (v1).
**Alias**: `POST /v1/search`

### Request
- Contract: `contracts/search-request.schema.json`
- Example: `contracts/examples/search-request.sample.json`

### Response
- Contract: `contracts/search-response.schema.json`
- Example: `contracts/examples/search-response.sample.json`

### Notes (MVP)
- If `query_context` is missing, BFF will derive it via QS using `query.raw` when present.
- Response includes `imp_id` + `query_hash` for search event logging.

## POST `/search/click`
**Purpose**: record a search result click event.
**Alias**: `POST /v1/search/click`

### Request
- Contract: `contracts/search-click-request.schema.json`
- Example: `contracts/examples/search-click-request.sample.json`

### Response
- Contract: `contracts/ack-response.schema.json`
- Example: `contracts/examples/ack-response.sample.json`

## POST `/search/dwell`
**Purpose**: record a search result dwell event.
**Alias**: `POST /v1/search/dwell`

### Request
- Contract: `contracts/search-dwell-request.schema.json`
- Example: `contracts/examples/search-dwell-request.sample.json`

### Response
- Contract: `contracts/ack-response.schema.json`
- Example: `contracts/examples/ack-response.sample.json`

## POST `/chat`
**Purpose**: RAG chat response with citations (BFF → QS `/chat`).  
**Alias**: `POST /v1/chat`

### Request
- Contract: `contracts/chat-request.schema.json`
- Example: `contracts/examples/chat-request.sample.json`

### Response
- Contract: `contracts/chat-response.schema.json`
- Example: `contracts/examples/chat-response.sample.json`

### Streaming (optional)
- `POST /chat?stream=true` returns `text/event-stream`
- Events:
  - `meta` (trace/request metadata)
  - `delta` (token chunk payload)
  - `error` (reason code/message when degraded)
  - `done` (final status + citations)

## POST `/chat/feedback`
**Purpose**: user feedback for chat answers (👍/👎 + flags).  
**Alias**: `POST /v1/chat/feedback`

### Request
- Contract: `contracts/chat-feedback-request.schema.json`
- Example: `contracts/examples/chat-feedback-request.sample.json`

### Response
- Contract: `contracts/ack-response.schema.json`

## GET `/autocomplete`
**Purpose**: return query suggestions for a prefix.

### Request (Query Params)
- `q` (string, optional): prefix. empty value returns trending/recommended suggestions.
- `size` (int, optional, default=10)

### Response (Planned MVP Shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "took_ms": 1,
  "suggestions": [
    { "text": "string", "score": 0.0, "source": "redis|opensearch", "suggest_id": "string", "type": "string" }
  ]
}
```

## GET `/categories/kdc`
**Purpose**: return KDC category tree (depth 0-2).

### Response
- Contract: `contracts/kdc-category-response.schema.json`
- Example: `contracts/examples/kdc-category-response.sample.json`

## POST `/autocomplete/select`
**Purpose**: record a suggestion selection event.

### Request
- Contract: `contracts/autocomplete-select-request.schema.json`
- Example: `contracts/examples/autocomplete-select-request.sample.json`

### Response
- Contract: `contracts/ack-response.schema.json`
- Example: `contracts/examples/ack-response.sample.json`

## GET `/books/{docId}`
**Purpose**: book detail by doc id.
**Alias**: `GET /v1/books/{docId}`

### Response (MVP Shape)
```json
{
  "doc_id": "string",
  "source": {},
  "trace_id": "string",
  "request_id": "string",
  "took_ms": 1
}
```

# 1.2) BFF Admin Ops (Internal/Admin)

**Responsibility**: operational visibility and control for reindex + batch jobs.

## GET `/admin/ops/job-runs`
**Purpose**: list recent job runs.  
**Query Params**: `limit` (int, optional), `status` (string, optional)  
**Response**: `contracts/job-run-list-response.schema.json`

## GET `/admin/ops/job-runs/{id}`
**Purpose**: get a single job run.  
**Response**: `contracts/job-run-response.schema.json`

## POST `/admin/ops/job-runs/{id}/retry`
**Purpose**: retry a failed job run (creates a new job_run row).  
**Response**: `contracts/job-run-response.schema.json`

## GET `/admin/ops/reindex-jobs`
**Purpose**: list reindex jobs.  
**Query Params**: `limit` (int, optional), `status` (string, optional), `logical_name` (string, optional)  
**Response**: `contracts/reindex-job-list-response.schema.json`

## POST `/admin/ops/reindex-jobs/start`
**Purpose**: start a new reindex job.  
**Request**: `contracts/reindex-job-create-request.schema.json`  
**Response**: `contracts/reindex-job-response.schema.json`

## BFF Admin Model Ops (Internal/Admin)

**Responsibility**: model registry visibility + rollout/canary + eval report access.

## GET `/admin/models/registry`
**Purpose**: list model registry state (proxy to MIS).  
**Response**: `contracts/mis-models-response.schema.json`

## POST `/admin/models/registry/activate`
**Purpose**: set an active model for a task (rollout/rollback).  
**Request (MVP)**:
```json
{ "model_id": "string", "task": "rerank" }
```
**Response**: `contracts/ack-response.schema.json`

## POST `/admin/models/registry/canary`
**Purpose**: set canary model + weight.  
**Request (MVP)**:
```json
{ "model_id": "string", "task": "rerank", "canary_weight": 0.05 }
```
**Response**: `contracts/ack-response.schema.json`

## POST `/admin/models/registry/rollback`
**Purpose**: rollback to a previous model (alias of activate).  
**Request/Response**: same as `/admin/models/registry/activate`

## GET `/admin/models/eval-runs`
**Purpose**: list offline eval reports (golden/shadow/hard).  
**Response (MVP shape)**:
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "count": 1,
  "items": [
    {
      "run_id": "string",
      "generated_at": "date-time",
      "sets": { "golden": { "ndcg_10": 0.0 } },
      "overall": { "ndcg_10": 0.0 }
    }
  ]
}
```

## BFF Admin RAG Ops (Internal/Admin)

**Responsibility**: document upload + index reindex/rollback + eval labeling.

## POST `/admin/rag/docs/upload`
**Purpose**: upload a RAG document (stored for later indexing).  
**Response**: `contracts/ack-response.schema.json`

## POST `/admin/rag/index/reindex`
**Purpose**: create a RAG reindex ops task.  
**Response**: `contracts/ack-response.schema.json`

## POST `/admin/rag/index/rollback`
**Purpose**: create a RAG rollback ops task.  
**Response**: `contracts/ack-response.schema.json`

## POST `/admin/rag/eval/label`
**Purpose**: store manual eval/label judgments for RAG answers.  
**Response**: `contracts/ack-response.schema.json`

## POST `/admin/ops/reindex-jobs/{id}/pause`
**Purpose**: pause a running reindex job.  
**Response**: `contracts/reindex-job-response.schema.json`

## POST `/admin/ops/reindex-jobs/{id}/resume`
**Purpose**: resume a paused reindex job.  
**Response**: `contracts/reindex-job-response.schema.json`

## POST `/admin/ops/reindex-jobs/{id}/retry`
**Purpose**: retry a failed reindex job.  
**Response**: `contracts/reindex-job-response.schema.json`

## GET `/admin/ops/tasks`
**Purpose**: list ops tasks.  
**Query Params**: `limit` (int, optional), `status` (string, optional), `task_type` (string, optional)  
**Response**: `contracts/ops-task-list-response.schema.json`

## GET `/admin/ops/autocomplete/suggestions`
**Purpose**: search autocomplete suggestions for ops review.  
**Query Params**: `q` (string), `size` (int, optional), `include_blocked` (bool, optional)  
**Response**: `contracts/autocomplete-admin-suggestions-response.schema.json`

## POST `/admin/ops/autocomplete/suggestions/{id}`
**Purpose**: update suggestion weight/blocking.  
**Request**: `contracts/autocomplete-admin-update-request.schema.json`  
**Response**: `contracts/autocomplete-admin-update-response.schema.json`

## GET `/admin/ops/autocomplete/trends`
**Purpose**: top suggestions by CTR/Popularity.  
**Query Params**: `metric` (ctr|popularity|impressions, optional), `limit` (int, optional)  
**Response**: `contracts/autocomplete-admin-trends-response.schema.json`

## GET `/admin/authority/merge-groups`
**Purpose**: list material merge groups (canonical selection queue).  
**Query Params**: `limit` (int, optional), `status` (string, optional)  
**Response**: `contracts/authority-merge-group-list-response.schema.json`

## POST `/admin/authority/merge-groups/{id}/resolve`
**Purpose**: mark a merge group as resolved by selecting a master material.  
**Request**: `contracts/authority-merge-group-resolve-request.schema.json`  
**Response**: `contracts/authority-merge-group-response.schema.json`

## GET `/admin/authority/agent-aliases`
**Purpose**: list author alias dictionary entries.  
**Query Params**: `limit` (int, optional), `q` (string, optional), `status` (string, optional)  
**Response**: `contracts/agent-alias-list-response.schema.json`

## POST `/admin/authority/agent-aliases`
**Purpose**: upsert an author alias entry.  
**Request**: `contracts/agent-alias-upsert-request.schema.json`  
**Response**: `contracts/agent-alias-response.schema.json`

## DELETE `/admin/authority/agent-aliases/{id}`
**Purpose**: delete (soft) an author alias entry.  
**Response**: `contracts/agent-alias-response.schema.json`

# 1.5) Index Writer Service (Internal)

**Responsibility**: managed reindex jobs (state machine, pause/resume/checkpoint).

## Base URL (Local)
`http://localhost:8090`

## POST `/internal/index/reindex-jobs`
**Purpose**: create a reindex job.  
**Request**: `contracts/reindex-job-create-request.schema.json`  
**Response**: `contracts/reindex-job-response.schema.json`

## GET `/internal/index/reindex-jobs/{id}`
**Purpose**: fetch job detail.  
**Response**: `contracts/reindex-job-response.schema.json`

## POST `/internal/index/reindex-jobs/{id}/pause`
**Purpose**: pause a running job.  
**Response**: `contracts/reindex-job-response.schema.json`

## POST `/internal/index/reindex-jobs/{id}/resume`
**Purpose**: resume a paused job.  
**Response**: `contracts/reindex-job-response.schema.json`

## POST `/internal/index/reindex-jobs/{id}/retry`
**Purpose**: retry a failed job.  
**Response**: `contracts/reindex-job-response.schema.json`

# 2) Query Service (QS)

**Responsibility**: Query normalization, lightweight understanding, and generation of `QueryContext`.

## GET `/health`
**Purpose**: liveness probe  
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## POST `/query/prepare`
**Purpose**: Convert user input into `QueryContext (qc.v1.1)` (primary endpoint).

### Request
**Body (JSON)** — **Preferred (official)**
```json
{
  "query": { "raw": "string" },
  "client": {},
  "user": {}
}
```

- `query.raw` (string, required): raw user query
- `client` (object|null, optional): arbitrary client metadata (locale, app, device)
- `user` (object|null, optional): arbitrary user metadata (user_id, segment)

**Backward compatibility (optional)**
```json
{ "raw": "string" }
```
If supported, the server should treat it as:
```json
{ "query": { "raw": "<raw>" } }
```

### Response
- Contract: `contracts/query-context-v1_1.schema.json`
- Example: `contracts/examples/query-context.sample.json`

### Notes (MVP)
- QS must:
  - normalize `query.raw` deterministically
  - populate `canonicalKey`, `detected`, `slots`, and default blocks
- `trace_id/request_id`:
  - If headers exist, propagate them
  - Otherwise generate them

## POST `/query-context` (Deprecated alias)
**Purpose**: Compatibility alias for `/query/prepare`.

### Request
- Contract: `contracts/query-prepare-request.schema.json`
- Example: `contracts/examples/query-prepare-request.sample.json`

### Response
- Contract: `contracts/query-context-v1_1.schema.json`
- Example: `contracts/examples/query-context.sample.json`

## POST `/query/enhance`
**Purpose**: Run 2-pass gating (spell/rewrite/RAG) and return decision + enhanced query.

### Request
- Contract: `contracts/query-enhance-request.schema.json`
- Example: `contracts/examples/query-enhance-request.sample.json`

### Response
- Contract: `contracts/query-enhance-response.schema.json`
- Example: `contracts/examples/query-enhance-response.sample.json`

## POST `/chat`
**Purpose**: RAG chat orchestration (rewrite → retrieve → generate with citations).

### Request
- Contract: `contracts/chat-request.schema.json`
- Example: `contracts/examples/chat-request.sample.json`

### Response
- Contract: `contracts/chat-response.schema.json`
- Example: `contracts/examples/chat-response.sample.json`

### Streaming (optional)
- `POST /chat?stream=true` or `options.stream=true` returns `text/event-stream`
- Events:
  - `meta`
  - `delta`
  - `error`
  - `done`

## POST `/internal/rag/explain`
**Purpose**: Internal retrieval debug trace (lexical/vector/fused/selected + rerank/rewrite reason codes).

### Request
- Same message/query envelope as `/chat` (internal use)

### Response (MVP shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "status": "ok",
  "query": {
    "text": "string",
    "locale": "string",
    "canonical_key": "string",
    "rewritten": "string"
  },
  "rewrite": {
    "rewrite_applied": true,
    "rewrite_reason": "RAG_LOW_SCORE",
    "rewrite_strategy": "rewrite"
  },
  "retrieval": {
    "top_n": 40,
    "top_k": 6,
    "lexical": [],
    "vector": [],
    "fused": [],
    "selected": [],
    "rerank": {},
    "took_ms": 12,
    "degraded": false
  },
  "reason_codes": ["RAG_RERANK_DISABLED"]
}
```

## GET `/internal/qc/rewrite/failures`
**Purpose**: List curated rewrite failure cases for replay/analysis.

### Response
- Contract: `contracts/query-rewrite-failure-response.schema.json`
- Example: `contracts/examples/query-rewrite-failure-response.sample.json`

---

# 3) Search Service (SS)

**Responsibility**: Retrieval orchestration (OpenSearch BM25/hybrid), filters/facets, and returning hits.

## GET `/health`
**Purpose**: liveness probe  
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## POST `/search`
**Purpose**: Execute retrieval using `SearchRequest (v1)` and return `SearchResponse (v1)`.
**Alias**: `POST /internal/search` (service-to-service)

### Request
- Contract: `contracts/search-request.schema.json`
- Example: `contracts/examples/search-request.sample.json`

### Response
- Contract: `contracts/search-response.schema.json`
- Example: `contracts/examples/search-response.sample.json`

### Notes (MVP)
- Primary query text should be `query_context.query.canonical`
- Pagination maps to OpenSearch `from/size`
- If `options.debug == true`, include `debug.query_dsl`
- Lexical retrieval should include multilingual fallback paths (phrase + ngram + contains fallback) so Korean compound-word substrings such as `영어교육`/`문화지도` can still match titles like `초등영어교육의 영미문화지도에 관한 연구`.

## POST `/internal/explain`
**Purpose**: Internal debug variant of search (forces explain/debug flags).

### Request
- Contract: `contracts/search-request.schema.json`

### Response
- Contract: `contracts/search-response.schema.json`

---

# 4) Autocomplete Service (ACS) — Planned

**Responsibility**: Prefix suggestions with low latency (Redis hot prefixes + OpenSearch prefix fallback).

## GET `/health`
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## GET `/autocomplete`
**Purpose**: Return query suggestions for a prefix.
**Alias**: `GET /internal/autocomplete` (service-to-service)

### Request (Query Params)
- `q` (string, required): prefix
- `size` (int, optional, default=10)

### Response (Planned MVP Shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "q": "string",
  "suggestions": [
    { "text": "string", "score": 0.0, "source": "redis|opensearch" }
  ]
}
```

---

# 5) Ranking Service (RS)

**Responsibility**: Re-rank candidate documents (LTR / cross-encoder).

## GET `/health`
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## POST `/rerank`
**Purpose**: Re-rank candidates for a query.
**Alias**: `POST /internal/rank` (service-to-service)

### Request (MVP)
```json
{
  "query": { "text": "string" },
  "candidates": [
    { "doc_id": "string", "features": { "rrf_score": 0.1, "lex_rank": 1, "vec_rank": 2 } }
  ],
  "options": { "size": 10, "debug": false, "rerank": true, "timeout_ms": 200 }
}
```

### Response (MVP)
```json
{
  "trace_id": "string",
  "request_id": "string",
  "model": "string",
  "hits": [
    { "doc_id": "string", "score": 0.0, "rank": 1, "debug": { "features": { "rrf_score": 0.1 } } }
  ],
  "debug": {
    "feature_set_version": "fs_v1",
    "reason_codes": ["size_capped"]
  }
}
```

---

# 6) Model Inference Service (MIS)

**Responsibility**: Centralized model inference (embeddings, scoring) with versioning and performance controls.

## GET `/health`
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## GET `/ready`
**Response**: `200 OK`
```json
{ "status": "ok|degraded", "models_ready": 0, "models_total": 0 }
```

## GET `/v1/models`
**Purpose**: List model registry state.

### Response
- Contract: `contracts/mis-models-response.schema.json`
- Example: `contracts/examples/mis-models-response.sample.json`

## POST `/v1/score`
**Purpose**: Score query-document pairs (e.g., cross-encoder).

### Request
- Contract: `contracts/mis-score-request.schema.json`
- Example: `contracts/examples/mis-score-request.sample.json`

### Response
- Contract: `contracts/mis-score-response.schema.json`
- Example: `contracts/examples/mis-score-response.sample.json`

## POST `/v1/spell`
**Purpose**: Spell correction for a single query text.

### Request
- Contract: `contracts/mis-spell-request.schema.json`
- Example: `contracts/examples/mis-spell-request.sample.json`

### Response
- Contract: `contracts/mis-spell-response.schema.json`
- Example: `contracts/examples/mis-spell-response.sample.json`

## POST `/embed`
**Purpose**: Generate embeddings for input texts (dev fallback).

### Request (MVP shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "model": "string",
  "texts": ["string"]
}
```

### Response (MVP shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "model": "string",
  "vectors": [[0.0, 0.0]]
}
```

---

# 7) LLM Gateway (LLMGW)

**Responsibility**: Centralized LLM calls with keys/quotas/retries/audit/cost control.

## GET `/health`
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## GET `/ready`
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## POST `/v1/generate`
**Purpose**: Generate a citation-aware response from context.

### Request (MVP shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "model": "string",
  "messages": [{ "role": "user", "content": "string" }],
  "context": { "chunks": [{ "citation_key": "doc#0", "content": "text" }] },
  "citations_required": true
}
```

### Response (MVP shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "model": "string",
  "content": "string",
  "citations": ["doc#0"],
  "tokens": 100,
  "cost_usd": 0.002
}
```

---

# 9) Commerce API (via BFF → Commerce Service)

## User (v1)
- `GET /api/v1/skus?materialId=...`
- `GET /api/v1/skus/{skuId}`
- `GET /api/v1/skus/{skuId}/offers`
- `GET /api/v1/skus/{skuId}/current-offer`
- `GET /api/v1/materials/{materialId}/current-offer`
- `GET /api/v1/home/panels?limit=31&type=EVENT|NOTICE`
- `GET /api/v1/cart`
- `POST /api/v1/cart/items`
- `PATCH /api/v1/cart/items/{cartItemId}`
- `DELETE /api/v1/cart/items/{cartItemId}`
- `DELETE /api/v1/cart/items`
- `GET /api/v1/checkout`
- `GET /api/v1/addresses`
- `POST /api/v1/addresses`
- `POST /api/v1/addresses/{addressId}/default`
- `POST /api/v1/orders`
- `GET /api/v1/orders`
- `GET /api/v1/orders/{orderId}`
- `POST /api/v1/orders/{orderId}/cancel`
- `POST /api/v1/payments`
- `GET /api/v1/payments/{paymentId}`
- `POST /api/v1/payments/{paymentId}/mock/complete`
- `POST /api/v1/payments/webhook/{provider}`
- `POST /api/v1/shipments`
- `POST /api/v1/shipments/{shipmentId}/tracking`
- `POST /api/v1/shipments/{shipmentId}/mock/status`
- `GET /api/v1/shipments/{shipmentId}`
- `GET /api/v1/shipments/by-order/{orderId}`
- `POST /api/v1/refunds`
- `GET /api/v1/refunds/{refundId}`
- `GET /api/v1/refunds/by-order/{orderId}`
- `POST /api/v1/support/tickets`
- `GET /api/v1/support/tickets`
- `GET /api/v1/support/tickets/{ticketId}`
- `GET /api/v1/support/tickets/by-number/{ticketNo}`
- `GET /api/v1/support/tickets/{ticketId}/events`

### Home Events/Notices
- `GET /api/v1/home/panels`
  - Query params
    - `limit` (optional, default `31`, max `100`)
    - `type` (optional: `EVENT` or `NOTICE`)
  - Response fields
    - `items[]`: `item_id`, `type`, `banner_image_url`, `badge`, `title`, `subtitle`, `summary`, `link_url`, `cta_label`, `starts_at`, `ends_at`, `sort_order`
    - `count`, `total_count`

### Orders (User)
- `GET /api/v1/orders`
  - Response fields
    - `items[]`: base order fields + `item_count`, `primary_item_title`, `primary_item_author`, `primary_item_material_id`, `primary_item_sku_id`
- `GET /api/v1/orders/{orderId}`
  - Response fields
    - `items[]`: base order item fields + `material_id`, `title`, `subtitle`, `author`, `publisher`, `issued_year`, `seller_name`, `format`, `edition`, `pack_size`
- `POST /api/v1/refunds`
  - Refund amount is policy-driven by order status and reason code.
  - Response fields (`refund`):
    - `item_amount`, `shipping_refund_amount`, `return_fee_amount`, `amount`, `policy_code`
  - Current policy summary:
    - `PAID` / `READY_TO_SHIP`: full refund request refunds shipping fee (partial refunds: shipping fee not refunded).
    - `SHIPPED` / `DELIVERED`: seller-fault reasons (`DAMAGED`, `DEFECTIVE`, `WRONG_ITEM`, `LATE_DELIVERY`) waive return fee; customer-remorse reasons apply return fee.
    - Return fee defaults to base/fast shipping fee by shipping mode.

### Support Tickets (User)
- `POST /api/v1/support/tickets`
  - Request fields
    - `orderId` (optional): 문의와 연결할 주문 ID
    - `category` (`GENERAL|ORDER|SHIPPING|REFUND|PAYMENT|ACCOUNT`)
    - `severity` (`LOW|MEDIUM|HIGH|CRITICAL`)
    - `summary` (required)
    - `details` (optional object)
    - `errorCode`, `chatSessionId`, `chatRequestId` (optional)
  - Response fields
    - `ticket`: `ticket_id`, `ticket_no`, `status`, `severity`, `expected_response_at`
    - `expected_response_minutes`
- `GET /api/v1/support/tickets/by-number/{ticketNo}`
  - Returns latest ticket state for owner only.
- `GET /api/v1/support/tickets/{ticketId}/events`
  - Returns lifecycle events (received/status changed, etc.)

## Admin (v1)
- `GET /admin/sellers`
- `POST /admin/sellers`
- `PATCH /admin/sellers/{sellerId}`
- `GET /admin/skus`
- `POST /admin/skus`
- `PATCH /admin/skus/{skuId}`
- `GET /admin/offers?sku_id=...`
- `POST /admin/offers`
- `PATCH /admin/offers/{offerId}`
- `GET /admin/inventory/balance?sku_id=...`
- `GET /admin/inventory/ledger?sku_id=...`
- `POST /admin/inventory/adjust`
- `GET /admin/payments`
- `GET /admin/payments/{paymentId}`
- `POST /admin/payments/{paymentId}/cancel`
- `GET /admin/refunds`
- `GET /admin/refunds/{refundId}`
- `POST /admin/refunds`
- `POST /admin/refunds/{refundId}/approve`
- `POST /admin/refunds/{refundId}/process`
- `GET /admin/shipments`
- `GET /admin/shipments/{shipmentId}`
- `POST /admin/shipments/{shipmentId}/label`
- `POST /admin/shipments/{shipmentId}/status`
- `POST /admin/support/tickets/{ticketId}/status`

---

## Minimal Smoke Commands (Local)

### QS: QueryContext
```bash
curl -s -XPOST http://localhost:8001/query/prepare \
  -H "Content-Type: application/json" \
  -H "x-trace-id: trace_demo" \
  -H "x-request-id: req_demo" \
  -d '{"query":{"raw":"해리포터 1권"}}'
```

### QS: QueryContext v1 (prepare)
```bash
curl -s -XPOST http://localhost:8001/query/prepare \
  -H "Content-Type: application/json" \
  -H "x-trace-id: trace_demo" \
  -H "x-request-id: req_demo" \
  -d '{"query":{"raw":"해리포터 Vol.1"}}'
```

### QS: Enhance (gating)
```bash
curl -s -XPOST http://localhost:8001/query/enhance \
  -H "Content-Type: application/json" \
  -d '{"request_id":"req_demo","trace_id":"trace_demo","q_norm":"해리포터 1권","q_nospace":"해리포터1권","detected":{"mode":"normal","is_isbn":false,"has_volume":true,"lang":"ko"},"reason":"ZERO_RESULTS","signals":{"latency_budget_ms":800,"score_gap":0.01}}'
```

### SS: Search (when implemented)
```bash
curl -s -XPOST http://localhost:8002/search \
  -H "Content-Type: application/json" \
  -d @contracts/examples/search-request.sample.json
```
