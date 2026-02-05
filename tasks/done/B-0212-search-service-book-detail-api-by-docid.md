# B-0212 — Search Service: Book Detail API (by docId)

## Goal
Add a minimal **Book Detail API** to Search Service so **web-user** can open a book detail page via deep link (`/book/:docId`) without relying on `sessionStorage`.

After this ticket:
- Search Service exposes a **read-only** endpoint to fetch a book document by `docId`
- Uses OpenSearch alias **`books_doc_read`** to retrieve the source document
- Propagates IDs deterministically (`trace_id`, `request_id`)
- Provides predictable error handling (404/503/500)

Non-goals:
- No DB
- No new OpenSearch indices/mappings
- No auth
- No aggregation/facets

---

## Must Read (SSOT)
- `AGENTS.md`
- `docs/API_SURFACE.md` (if present)
- `docs/ARCHITECTURE.md` (if present)
- Existing Search Service error/response conventions

---

## Scope

### Allowed
- `services/search-service/**`
- `docs/RUNBOOK.md` (optional: add a short curl snippet)

### Forbidden
- `contracts/**`
- `infra/**`
- `db/**`
- `services/query-service/**`
- `services/ranking-service/**`

---

## API

### Endpoint
Add **one** of the following (pick the one that best fits existing controller style):

**Option A (preferred):**
- `GET /books/{docId}`

**Option B:**
- `GET /book/{docId}`

Keep it simple and REST-like.

### Headers (ID propagation)
- Read optional:
  - `x-trace-id`
  - `x-request-id`
- If missing: generate UUID-based IDs (same logic as `/search` legacy path)

### Response (200)
Return a small, stable payload:
```json
{
  "doc_id": "b1",
  "source": {
    "title_ko": "...",
    "authors": ["..."],
    "publisher_name": "...",
    "issued_year": 1999,
    "volume": 1,
    "edition_labels": ["recover"]
  },
  "trace_id": "...",
  "request_id": "...",
  "took_ms": 12
}
```
Notes:
- `source` should be the same mapped shape you already return inside `/search` hits (reuse mapper).
- If the underlying OpenSearch `_source` has additional fields, you may ignore them for MVP.

### Errors
Follow the existing error response convention:
```json
{ "error": { "code": "...", "message": "..." }, "trace_id": "...", "request_id": "..." }
```

- **404** if `docId` not found
  - `code`: `not_found`
- **503** if OpenSearch is unavailable
  - `code`: `opensearch_unavailable`
- **500** unexpected
  - `code`: `internal_error`

---

## Implementation Requirements

### 1) OpenSearch access
Use the existing `OpenSearchGateway`.

Add a new gateway method (or reuse an existing `mgetSources` if available):
- `getSourceById(String docId, Integer timeoutMs)` OR
- `mgetSources(List<String> docIds, Integer timeoutMs)` then pick the single result

Target index alias:
- `books_doc_read`

Timeout:
- Use a small default (e.g., 200ms) or reuse existing Search Service timeouts.
- Best-effort only.

### 2) Controller
Add a new controller endpoint:
- Validate `docId` is non-blank.
- Call gateway.
- If missing -> 404.
- Map `_source` -> `BookHit.Source` (or an equivalent DTO) to keep UI consistent.

### 3) Deterministic IDs
- Echo `trace_id` and `request_id` in response exactly.
- Prefer the same extraction logic as `/search` (headers first).

### 4) Unit tests
Add MockMvc tests:
1. `GET /books/b1` returns 200 with `doc_id=b1` and `trace_id/request_id` echoed
2. `GET /books/does_not_exist` returns 404 with error shape
3. OpenSearch unavailable -> 503

Mock `OpenSearchGateway` responses.

---

## Manual Validation

### Prereqs
- OpenSearch running with alias:
  - `books_doc_read`

### Run Search Service
```bash
cd services/search-service
./gradlew bootRun
```

### Curl
```bash
curl -s "http://localhost:8080/books/b1" \
  -H 'x-trace-id: trace_demo' \
  -H 'x-request-id: req_demo' | jq .
```

Expected:
- `doc_id == "b1"`
- `trace_id == "trace_demo"`
- `request_id == "req_demo"`

---

## Output (Dev Summary)
- List changed files
- How to run unit tests
- Curl example
- Known limitations (MVP fields only)
