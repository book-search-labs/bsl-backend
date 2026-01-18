# U-0107 — Web User: Search Page (MVP) — Query Service → Search Service (qc.v1.1)

## Goal
Implement the **real Search page** in **web-user** so users can search books end-to-end:

**Web User → Query Service (`/query-context`) → Search Service (`/search`) → Render results**

After this ticket:
- `/search` reads `q` from the URL
- User can submit a query from the global header search bar (already done in T-0106)
- SearchPage calls Query Service to build **qc.v1.1**
- SearchPage forwards that qc payload to Search Service using **`query_context_v1_1`**
- Render a clean results list (title / authors / publisher / year / volume / edition labels)
- Each hit links to `/book/:docId` (detail page is still placeholder for now)

Non-goals:
- No auth, cart, purchase, reservation, reviews yet
- No advanced filters UI
- No pagination UX polish (basic “Load more” optional)
- No new UI kit dependencies

---

## Must Read (SSOT)
- `AGENTS.md` (repo rules)
- `apps/web_user/README.md` (if exists)

---

## Scope

### Allowed
- `apps/web_user/**`

### Forbidden
- `apps/web_admin/**`
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
{
  "query": { "raw": "해리" },
  "client": { "device": "web_user" },
  "user": null
}
```
- Response: **qc.v1.1** (must include `meta.schemaVersion = "qc.v1.1"`)

### Search Service
- `POST {VITE_SEARCH_BASE_URL}/search`
- Request:
```json
{
  "query_context_v1_1": { "...qc.v1.1..." },
  "options": { "size": 10, "from": 0, "debug": false }
}
```

---

## Environment Variables
Create or ensure `apps/web_user/.env.example` exists:

- `VITE_QUERY_BASE_URL=http://localhost:8001`
- `VITE_SEARCH_BASE_URL=http://localhost:8080`

Do NOT commit `.env` (example only).

---

## Implementation Requirements

### 1) API helper (small + safe)
Create `src/lib/api.ts`:
- `postJson<T>(url, body, { timeoutMs })`
- Uses `AbortController` for timeout (e.g., 5000ms)
- Throws a typed error including status + response body (if JSON)

No new dependencies.

---

### 2) Search client functions
Create `src/features/search/searchApi.ts`:
- `fetchQueryContext(rawQuery: string)` → qc.v1.1 JSON
- `fetchSearch(qcV11: object, options)` → SearchResponse JSON

Validation:
- If Query Service response doesn’t contain `meta.schemaVersion === "qc.v1.1"`, show error.

---

### 3) SearchPage UI behavior
File: `src/pages/SearchPage.tsx` (or your existing location)

Must do:
- Read `q` from `useSearchParams()`
- Show:
  - Page title: “Search”
  - Small subtitle: `Results for: "<q>"`
  - Loading indicator while fetching
  - Error banner if either call fails (include status/message)
- Trigger search when:
  - `q` exists and changes (debounce NOT required; just react to URL changes)

Controls (minimal):
- Result size select or input (default 10)
- Vector enabled toggle (default true)
- Debug toggle (default false)

Request rule:
- Always call Query Service first to get qc.v1.1
- Before calling Search Service:
  - If Vector toggle is off, ensure:
    - `qc.retrievalHints.vector.enabled = false` (create objects if missing)
  - If Debug toggle is on:
    - send `options.debug = true`
  - size/from:
    - `options.size = size`
    - `options.from = 0` (MVP)

---

### 4) Render results list
Render hits in a clean list/cards (Bootstrap only):

For each hit:
- Title (link to `/book/:docId`)
- Authors (comma-separated)
- Publisher
- Year
- Volume
- Edition labels

Example fields from Search Service:
- `hit.doc_id`
- `hit.source.title_ko`
- `hit.source.authors` (array of strings)
- `hit.source.publisher_name`
- `hit.source.issued_year`
- `hit.source.volume`
- `hit.source.edition_labels` (array of strings)

Empty states:
- If `q` missing → show “Type a query to search.”
- If no hits → show “No results.”

Optional (nice-to-have):
- A small meta row:
  - `strategy`, `took_ms`, `ranking_applied` (only show if debug enabled)

---

### 5) Keep router intact
Do not change routes introduced in T-0106.
Just ensure `/search` page is now “real”.

---

## Acceptance Tests (Manual)

### Pre-req: services running
- Query Service: `http://localhost:8001`
- Search Service: `http://localhost:8080`
- OpenSearch up with aliases ready (`books_doc_read`, `books_vec_read`, etc.)

### Run web-user
```bash
cd apps/web_user
npm install
cp .env.example .env
npm run dev -- --port 5174
```

### Verify
1) Open `http://localhost:5174/`
2) Use global header search input, type `해리`, submit
3) App navigates to `/search?q=해리`
4) SearchPage:
   - Calls Query Service → gets qc.v1.1
   - Calls Search Service → renders results
5) Toggle “Vector off”:
   - Strategy should switch to BM25 on server side (e.g., `bm25_v1_1`)
6) Stop Query Service and retry:
   - UI shows a friendly error banner (not a crash)

---

## Deliverables
- Summary of created/changed files
- How to run locally
- One screenshot or short note confirming E2E works

---

## Suggested commit message
`feat(web-user)(U-0107): implement search page E2E via qc.v1.1 (query-service -> search-service)`
