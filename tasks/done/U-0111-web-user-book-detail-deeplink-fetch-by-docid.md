# U-0111 — Web User: Book Detail Deep Link (fetch by docId)

## Goal
Upgrade **web-user** book detail page so it works with deep links:

- User can open `/book/:docId` directly (new tab / refresh / share link)
- If book data is not in `sessionStorage`, fetch it from Search Service **B-0212**

After this ticket:
- BookDetail page shows content reliably in all navigation paths
- The existing “selected book” sessionStorage fast-path still works
- Friendly loading + error UI

Non-goals:
- No auth
- No server-side rendering
- No new endpoints beyond **B-0212**

---

## Must Read (SSOT)
- `AGENTS.md`
- `apps/web-user/README.md`
- Existing routing from U-0106
- Existing results UI from U-0108
- Existing Book Detail page from U-0109

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
- Search Service running: `http://localhost:8080`
  - Must include **B-0212** endpoint: `GET /books/:docId`
- Web-user runs on fixed port:
  - `http://localhost:5174`

---

## Environment Variables
Ensure `apps/web-user/.env.example` includes (or update if naming differs):

```env
VITE_SEARCH_SERVICE_BASE_URL=http://localhost:8080
VITE_QUERY_SERVICE_BASE_URL=http://localhost:8001
```

Notes:
- Only `VITE_SEARCH_SERVICE_BASE_URL` is required for this ticket.
- Ensure `.env` is gitignored.

---

## Implementation Requirements

### 1) Add API client for book detail
Create (or extend) a tiny API module:

- `src/api/http.ts`
  - `fetchJson<T>(url, init?)` with JSON handling + typed error

- `src/api/books.ts`
  - `getBookByDocId(docId: string)`
  - Calls:
    - `GET {VITE_SEARCH_SERVICE_BASE_URL}/books/{docId}`

Define minimal types:
```ts
type BookSource = {
  title_ko?: string | null
  authors?: string[]
  publisher_name?: string | null
  issued_year?: number | null
  volume?: number | null
  edition_labels?: string[]
}

type BookDetailResponse = {
  doc_id: string
  source: BookSource | null
  trace_id: string
  request_id: string
  took_ms: number
}
```

### 2) Update BookDetail page behavior
In `src/pages/BookDetailPage.tsx` (or your current file):

- Read `docId` from route params
- Try to load from sessionStorage first:
  - Key should match what U-0109 used (do not change the key name if already established)
  - If it matches the same `docId`, render immediately
- If sessionStorage is missing or does not match:
  - Fetch via `getBookByDocId(docId)`

UI states:
- Loading skeleton or spinner
- Error banner with:
  - HTTP status
  - message
  - “Retry” button
- Not found (404) message: “Book not found”

### 3) Keep navigation consistent
From search results:
- Clicking a hit still:
  - writes the selected hit to sessionStorage
  - navigates to `/book/:docId`

Book detail page:
- Provide a “Back to search” link
  - If a last search URL exists in sessionStorage, use it
  - Otherwise default to `/search`

### 4) Port and run docs
Update `apps/web-user/README.md` (or create) to remind:
- `npm run dev -- --port 5174`

---

## Acceptance Tests (Manual)

### Setup
```bash
# Search Service
cd services/search-service
./gradlew bootRun

# Web-user
cd apps/web-user
npm install
cp .env.example .env
npm run dev -- --port 5174
```

### Validate
1) Search results → click a book
- Detail page renders instantly (sessionStorage path)

2) Refresh on detail page
- Still renders (network fetch path)

3) Open in new tab directly
- `http://localhost:5174/book/b1`
- Renders after loading

4) Non-existent docId
- `http://localhost:5174/book/does_not_exist`
- Shows “not found” state (404)

---

## Output (Dev Summary)
- List changed/created files
- How to run locally
- Known limitations (no reviews/purchase/reservation yet)
