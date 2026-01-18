# U-0108 — Web User: Search Results UX Upgrade (Cards, Filters-lite, Pagination)

## Goal
Upgrade **Web User** search experience so `/search` feels like a real **book platform** search page (not a JSON debug view).

After this ticket:
- Search results render as **book cards** (title, authors, publisher, year, volume, edition labels)
- User gets clear **loading / error / empty** states
- Supports **pagination** (from/size) and basic **sorting UI** (client-side choice; server mapping later)
- Provides lightweight **filters UI** (“filters-lite”) that maps to **qc.v1.1 retrievalHints.filters** when E2E is enabled in U-0110
- Keeps dependencies minimal (use existing Bootstrap + React Router)

Non-goals:
- No auth/login
- No purchase/reservation/review flows yet
- No advanced facet counts from OpenSearch
- No new state libraries (Redux/Zustand)

---

## Must Read (SSOT)
- `AGENTS.md` (repo rules)
- `apps/web_user/README.md` (if present)
- T-0106 output (AppShell + routes)
- U-0107 implementation (SearchPage MVP)

---

## Scope

### Allowed
- `apps/web_user/**`

### Forbidden
- `services/**`
- `contracts/**`
- `infra/**`
- `db/**`

---

## UI Requirements

### 1) Search page layout (`/search`)
Create a clean, book-platform-like structure:

**Top row**
- Page title: **Search**
- Result meta: `"{totalDisplayed}" results` (if total not available, show `"Showing N"`)

**Left column (desktop) / collapsible (mobile)** — *Filters-lite*
- **Volume** (number input)
- **Edition label** (checkboxes; MVP values): `recover`, `limited`, `special` (static list)
- **Language** (dropdown; MVP values): `ko`, `en` (optional)
- Buttons:
  - `Apply`
  - `Reset`

**Right column**
- Sorting bar:
  - Sort dropdown (MVP options):
    - `Relevance` (default)
    - `Newest` (UI only; no server mapping yet)
    - `Oldest` (UI only)
- Results list grid:
  - Desktop: 2–3 columns
  - Mobile: 1 column

**Bottom row**
- Pagination controls:
  - Prev / Next
  - Page indicator (e.g., `Page 2`)

---

## Data/State Requirements

### 2) URL as the source of truth
Keep search state shareable via URL.

Use query params:
- `q` (string)
- `page` (1-based, default 1)
- `size` (default 10)
- `volume` (optional)
- `edition` (optional, multi: `edition=recover&edition=limited`)
- `lang` (optional)
- `sort` (optional: `relevance|newest|oldest`)

Rules:
- When user changes filters/sort/page, update URL.
- When URL changes (back/forward), UI reflects it.

---

## Networking (MVP)

### 3) Search request strategy
This ticket must work **without requiring Query Service**.

Use the same approach as your current U-0107 (whichever exists):
- **Option A (preferred if already implemented):** call Search Service directly with legacy shape:
  ```json
  {
    "query": { "raw": "해리" },
    "options": { "size": 10, "from": 0, "enableVector": true, "rrfK": 60, "debug": false }
  }
  ```
- **Option B:** if U-0107 already uses qc.v1.1 via Query Service, keep it (but U-0110 is the dedicated E2E ticket).

### 4) Map filters-lite into request (best-effort)
If using legacy request, pass filters only as **client-side filtering** (MVP):
- After results return, filter by:
  - volume equals
  - edition_labels contains any selected
  - language_code equals

If using qc.v1.1 already, map to:
```json
"retrievalHints": {
  "filters": [
    { "and": [
      { "scope": "CATALOG", "logicalField": "volume", "op": "eq", "value": 1, "strict": false, "reason": "UI_FILTER" }
    ] }
  ]
}
```

> Note: Full server-side filter correctness is ensured in **U-0110** (qc.v1.1 E2E). Here it’s OK to be MVP.

---

## Components & Files

### 5) Suggested structure
Create (or update) these files:
- `apps/web_user/src/pages/SearchPage.tsx` (main page)
- `apps/web_user/src/components/search/SearchFilters.tsx`
- `apps/web_user/src/components/search/SearchSortBar.tsx`
- `apps/web_user/src/components/search/SearchResultsGrid.tsx`
- `apps/web_user/src/components/search/BookCard.tsx`
- `apps/web_user/src/components/search/PaginationBar.tsx`
- `apps/web_user/src/lib/api.ts` (fetch wrapper with timeout)
- `apps/web_user/src/lib/urlState.ts` (parse/build URL params)

Keep CSS minimal:
- `apps/web_user/src/styles/app.css` (or existing stylesheet)

---

## UX Details

### 6) Loading / Error / Empty states
- Loading: skeleton-like placeholders (simple gray blocks OK)
- Error: bootstrap `alert-danger` with status + message
- Empty:
  - Title: `No results`
  - Suggestion: `Try a different query or remove filters.`

### 7) Click behavior
- Clicking a BookCard navigates to `/book/:docId`
- Preserve current search context in URL (no extra state)

---

## Acceptance

### Local run
```bash
cd apps/web_user
npm install
cp .env.example .env
npm run dev -- --port 5174
```

### Done when
1) `/search?q=해리` shows results as cards (not raw JSON)
2) Pagination works (`page` changes `from` correctly)
3) Filters-lite updates the URL and affects displayed results (server-side or client-side MVP is OK)
4) Loading/error/empty states are visible and stable
5) No new dependencies added unless absolutely necessary

---

## Deliverables
- List of changed/created files
- How to run locally
- Notes on what is still MVP (server-side filter accuracy if legacy request is used)
