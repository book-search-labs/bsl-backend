# T-0105 — Admin: Search Playground E2E (Query Service → Search Service)

## Goal
Add a **minimal “Search Playground” page** to **Web Admin** that verifies the full request path:

**Admin UI → Query Service (`/query-context`) → Search Service (`/search`)**

After this ticket:
- Admin can submit a raw query string
- Admin calls Query Service to obtain **qc.v1.1 QueryContext**
- Admin forwards that QueryContext to Search Service using **`query_context_v1_1`** request shape
- Admin renders hits + key debug fields (strategy / took_ms / stages / applied_fallback_id)
- Admin supports `.env` wiring for service base URLs

Non-goals:
- No styling perfection / no design system work
- No auth
- No persistence
- No advanced filters UI (beyond a simple “Vector on/off” toggle)

---

## Must Read (SSOT)
- `AGENTS.md` (repo rules)
- `apps/web_admin/README.md` (if present)
- `docs/RUNBOOK.md` (add a short snippet only if needed)

---

## Scope

### Allowed
- `apps/web_admin/**`
- `docs/RUNBOOK.md` (optional: add one short “Admin E2E” section)

### Forbidden
- `services/**`
- `contracts/**`
- `infra/**`
- `db/**`

---

## Background / Interfaces

### Query Service
- `POST {VITE_QUERY_BASE_URL}/query-context`
- Request:
```json
{ "query": { "raw": "해리" }, "client": { "device": "web_admin" }, "user": null }
```
- Response: **qc.v1.1** (must include `meta.schemaVersion="qc.v1.1"`)

### Search Service
- `POST {VITE_SEARCH_BASE_URL}/search`
- Request:
```json
{ "query_context_v1_1": { ...qc.v1.1... }, "options": { "size": 5, "from": 0, "debug": true } }
```

---

## Implementation Requirements

### 1) Environment variables (.env)
Add:
- `apps/web_admin/.env.example`

Must include:
- `VITE_QUERY_BASE_URL=http://localhost:8001`
- `VITE_SEARCH_BASE_URL=http://localhost:8080`

Ensure `.env` is ignored (either in root `.gitignore` or `apps/web_admin/.gitignore`).

---

### 2) Route: Search Playground
Add a route like:
- `/search-playground`

Add a nav link in the sidebar/menu to reach it.

---

### 3) UI: Minimal Controls
On the page, render:

**Inputs**
- Raw Query text input (default: `"해리"`)
- Result size number input (default: 5)
- Vector enabled checkbox (default: true)
- Debug checkbox (default: true)

**Buttons**
- `Run` (executes E2E chain)
- `Reset` (optional)

**Panels**
- “QueryContext (qc.v1.1)” JSON preview (collapsible is fine)
- “Search Response” JSON preview (collapsible is fine)
- “Hits” list (title/authors/publisher/year/volume/edition_labels)

Also show key meta fields:
- `traceId`, `requestId` (from qc response)
- `strategy`, `took_ms`, `ranking_applied`
- `debug.stages`, `debug.applied_fallback_id`, `debug.query_text_source_used`

---

### 4) Networking: E2E call sequence
When clicking `Run`:
1) Call Query Service `/query-context` with `{ query.raw }`
2) Validate response contains:
   - `meta.schemaVersion === "qc.v1.1"`
3) Call Search Service `/search` with:
   - `query_context_v1_1: <qc response>`
   - `options: { size, from: 0, debug }`
4) If “Vector enabled” is unchecked:
   - Mutate qc payload before sending to search:
     - `query_context_v1_1.retrievalHints.vector.enabled = false` (create objects if missing)

Do **not** invent new API fields.

---

### 5) Error handling
For both calls:
- Show a friendly error banner with HTTP status + message
- Render the raw error response body JSON if available

---

## Acceptance Tests (Manual)

### Pre-req: services running
- Query Service: `http://localhost:8001`
- Search Service: `http://localhost:8080`
- OpenSearch up with `books_doc_read` / `books_vec_read` aliases

### Run Admin
```bash
cd apps/web_admin
npm install
cp .env.example .env
npm run dev -- --port 5174
```

### Verify (Done when)
1) Open `http://localhost:5174/search-playground`
2) Enter query `해리`, click `Run`
3) UI shows:
   - qc.v1.1 JSON returned from Query Service
   - Search response JSON and a hits list
   - `strategy` is `hybrid_rrf_v1_1` when vector enabled
4) Toggle vector off, click `Run`
   - `strategy` becomes `bm25_v1_1`
5) Errors (stop Query Service) show a clear error banner instead of crashing

---

## Dev Notes
- Prefer a tiny `api.ts` helper for fetch:
  - JSON request/response
  - timeout via AbortController (e.g., 5s)
- Keep dependencies minimal (use what’s already in `package.json`).
