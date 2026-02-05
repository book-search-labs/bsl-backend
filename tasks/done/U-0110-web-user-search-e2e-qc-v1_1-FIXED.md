# U-0110 — Web User: Search E2E via Query Service (qc.v1.1) → Search Service (/search)

## Goal
Wire **web-user** so the search flow uses the real backend pipeline:

`Web User → Query Service (/query-context, qc.v1.1) → Search Service (/search, query_context_v1_1) → Results`

After this ticket:
- Web-user calls Query Service to obtain **qc.v1.1**
- Web-user forwards that qc.v1.1 to Search Service using the `query_context_v1_1` request shape
- Results render using the existing Results UI (U-0108) and Book Detail page (U-0109)
- A lightweight **Debug** toggle can show `strategy / took_ms` and optional debug fields

Non-goals:
- No auth
- No SSR
- No new backend endpoints
- No advanced filters/facets yet (separate tickets)

---

## Must Read (SSOT)
- `apps/web-user/README.md` (or your run docs)
- `apps/web-user/.env.example` (base URLs)

---

## Scope

### Allowed
- `apps/web-user/**`

### Forbidden
- `apps/web-admin/**`
- `services/**`
- `contracts/**`
- `infra/**`
- `db/**`

---

## Prerequisites (Local)
You must be able to run:
- Query Service: `http://localhost:8001/query-context`
- Search Service: `http://localhost:8080/search`
- OpenSearch locally with `books_doc_read` / `books_vec_read` aliases

---

## Environment Variables
Ensure `apps/web-user/.env.example` includes (create if missing):

```env
VITE_QUERY_BASE_URL=http://localhost:8001
VITE_SEARCH_BASE_URL=http://localhost:8080
```

Also ensure `.env` is gitignored.

---
## Prerequisites (Local)
You must be able to run:
- Query Service: `http://localhost:8001/query-context`
- Search Service: `http://localhost:8080/search`
- OpenSearch running locally with `books_doc_read` / `books_vec_read` aliases

## Environment Variables
Ensure `apps/web-user/.env.example` includes (use the same naming convention as Admin to keep it consistent):

```env
VITE_QUERY_BASE_URL=http://localhost:8001
VITE_SEARCH_BASE_URL=http://localhost:8080
```

Also ensure `.env` is gitignored.

---

## Implementation Requirements

### 1) Create a tiny API client layer
Add a minimal `src/api/` module:

- `src/api/http.ts`
  - `fetchJson<T>(url, init?)`
  - Sets JSON headers
  - Non-2xx → throws a typed error containing `status` and best-effort `body`
  - Supports a timeout via `AbortController` (e.g. 5s)

- `src/api/queryService.ts`
  - `postQueryContext(rawQuery: string, clientInfo?: object)` → returns qc.v1.1 JSON
  - Request:
    - `POST {VITE_QUERY_BASE_URL}/query-context`
    - Body:
      ```json
      { "query": { "raw": "..." }, "client": { "device": "web_user" }, "user": null }
      ```
  - MVP: do not generate trace/request ids client-side (let backend generate). Optionally, you may pass through ids if you already have them.

- `src/api/searchService.ts`
  - `postSearchWithQc(qc: unknown, options: { size: number; from: number; debug?: boolean })`
  - Request:
    - `POST {VITE_SEARCH_BASE_URL}/search`
    - Body:
      ```json
      { "query_context_v1_1": { ...qc... }, "options": { "size": 5, "from": 0, "debug": true } }
      ```

Types:
- MVP is OK with `type QcV11 = any`.
- Define a small `SearchResponse` type for what you render: `hits`, `strategy`, `took_ms`, `trace_id`, `request_id`, and optional `debug`.

---

### 2) Update Search page to use the pipeline
In `src/pages/SearchPage.tsx` (or your search container), implement:

1. Read `q` from the URL: `/search?q=...`
2. If `q` exists on initial load, auto-run the search once.
3. On submit:
   - Set loading state
   - Call Query Service → get qc.v1.1
   - Validate `qc.meta.schemaVersion === "qc.v1.1"`
   - Optionally mutate qc based on UI toggles (see below)
   - Call Search Service with `{ query_context_v1_1: qc, options: ... }`
   - Render results using existing UI from U-0108
4. Store the last qc and search response in state for the Debug panel.

Error handling:
- Show an inline error banner with HTTP status + message
- Include a “Retry” button to rerun the same query
- Never crash the page on fetch errors

---

### 3) Minimal controls (MVP)
On the search page, add a small control row above results:
- Result size (default 10, clamp 1..50)
- Vector enabled toggle (default on)
- Debug toggle (default off)

When “Vector enabled” is off:
- Before sending qc to Search Service, ensure:
  - `qc.retrievalHints.vector.enabled = false`
  - (MVP) do not alter other hints

When “Debug” is on:
- Send `options.debug = true`
- Show:
  - `strategy`, `took_ms`, `trace_id`, `request_id`
  - If present: `response.debug.stages`, `response.debug.applied_fallback_id`, `response.debug.query_text_source_used`

---

### 4) Keep URL in sync
- Submitting the header/global search should navigate to `/search?q=<encoded>` (already done in T-0106 shell)
- SearchPage should treat the URL as the source of truth:
  - If the URL changes (back/forward), rerun the search

Debounce:
- Optional. Submit-only is fine for this ticket.

---

### 5) Book Detail navigation (U-0109 integration)
When a user clicks a hit:
- Navigate to `/book/:docId` (match your router from T-0106)
- Persist the clicked hit in `sessionStorage` (as done in U-0109)
- Book detail page reads from storage; if missing, show a friendly fallback message

No new backend call is required for detail in this ticket.

---

## Acceptance Tests (Manual)

### A) Run backend
```bash
# Query Service
cd services/query-service
uvicorn app.main:app --reload --port 8001

# Search Service
cd services/search-service
./gradlew bootRun
```

### B) Run web-user (port is fixed)
```bash
cd apps/web-user
npm install
cp .env.example .env
npm run dev -- --port 5174
```

### C) Validate
1. Open `http://localhost:5174/search`
2. Search for `해리`
3. Results render and show strategy (expected: `hybrid_rrf_v1_1` when vector enabled)
4. Toggle Vector off → rerun → strategy becomes `bm25_v1_1`
5. Toggle Debug on → see ids and stages/fallback if present
6. Click a hit → navigates to `/book/<docId>` and shows stored details
7. Back button returns to `/search?q=해리`

---

## Output (Dev Summary)
- Changed/created files list
- How to run locally
- Notes on what is still MVP (no facets, no server-side book detail fetch)
