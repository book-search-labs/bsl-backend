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

### Request
- Contract: `contracts/search-request.schema.json`
- Example: `contracts/examples/search-request.sample.json`

### Response
- Contract: `contracts/search-response.schema.json`
- Example: `contracts/examples/search-response.sample.json`

### Notes (MVP)
- If `query_context` is missing, BFF will derive it via QS using `query.raw` when present.

## GET `/autocomplete`
**Purpose**: return query suggestions for a prefix.

### Request (Query Params)
- `q` (string, required): prefix
- `size` (int, optional, default=10)

### Response (Planned MVP Shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "took_ms": 1,
  "suggestions": [
    { "text": "string", "score": 0.0, "source": "redis|opensearch" }
  ]
}
```

## GET `/books/{docId}`
**Purpose**: book detail by doc id.

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

## POST `/query-context`
**Purpose**: Convert user input into `QueryContext (v1)`.

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
- `200 OK`
- Contract: `contracts/query-context.schema.json`
- Example: `contracts/examples/query-context.sample.json`

### Notes (MVP)
- QS must:
  - normalize `query.raw` deterministically
  - set `query.canonical` = `query.normalized` (MVP)
  - fill default blocks: `spell`, `rewrite`, `understanding`, `retrieval_hints`
- `trace_id/request_id`:
  - If headers exist, propagate them
  - Otherwise generate them

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

# 5) Ranking Service (RS) — Planned

**Responsibility**: Re-rank candidate documents (LTR / cross-encoder).

## GET `/health`
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## POST `/rerank`
**Purpose**: Re-rank candidates for a query.

### Request (Planned)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "query_context": { "..." : "QueryContext v1" },
  "candidates": [{ "doc_id": "string" }],
  "top_k": 10
}
```

### Response (Planned)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "reranked": [
    { "doc_id": "string", "score": 0.0, "rank": 1 }
  ]
}
```

---

# 6) Model Inference Service (MIS) — Planned

**Responsibility**: Centralized model inference (embeddings, scoring) with versioning and performance controls.

## GET `/health`
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## POST `/embed`
**Purpose**: Generate embeddings for input texts.

### Request (Planned)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "model": "string",
  "texts": ["string"]
}
```

### Response (Planned)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "model": "string",
  "vectors": [[0.0, 0.0]]
}
```

## POST `/score`
**Purpose**: Score query-document pairs (e.g., cross-encoder).

### Request (Planned)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "model": "string",
  "pairs": [{ "query": "string", "doc": "string" }]
}
```

### Response (Planned)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "model": "string",
  "scores": [0.0]
}
```

---

## Minimal Smoke Commands (Local)

### QS: QueryContext
```bash
curl -s -XPOST http://localhost:8001/query-context \
  -H "Content-Type: application/json" \
  -H "x-trace-id: trace_demo" \
  -H "x-request-id: req_demo" \
  -d '{"query":{"raw":"해리포터 1권"}}'
```

### SS: Search (when implemented)
```bash
curl -s -XPOST http://localhost:8002/search \
  -H "Content-Type: application/json" \
  -d @contracts/examples/search-request.sample.json
```
