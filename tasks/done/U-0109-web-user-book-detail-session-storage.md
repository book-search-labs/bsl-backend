# U-0109 — Web User: Book detail page + sessionStorage handoff (MVP)

## Goal
Upgrade **web-user** so clicking a search result opens a **Book Detail** page that can render meaningful content **without adding any new backend endpoints**.

After this ticket:
- Search results items link to `/book/:docId`
- The selected item is saved to **sessionStorage** on click
- `BookDetailPage` can render details using:
  1) `location.state` (preferred, same-session navigation)
  2) `sessionStorage` fallback (page refresh / deep link)
- A small “Recently viewed” section is shown (last 5 items, session-only)

Non-goals:
- No purchase / reservation / review features yet
- No user auth
- No server-side book detail endpoint

---

## Must Read (SSOT)
- `AGENTS.md`
- `apps/web_user/README.md` (if present)

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

## Background / Assumptions
- U-0108 already renders a search results list (or at least a basic list).
- Search results are derived from Search Service `/search` response (hits include `doc_id`, `source`, maybe `debug`).

We will store a **small normalized book payload** (docId + minimal fields) rather than the entire raw API response.

---

## Implementation Requirements

### 1) Define a tiny “BookSummary” type
Create `src/types/book.ts`:
- `export type BookSummary = { docId: string; titleKo?: string | null; authors?: string[]; publisherName?: string | null; issuedYear?: number | null; volume?: number | null; editionLabels?: string[] }`

Also add helpers:
- `export function toBookSummary(hit: any): BookSummary` (defensive mapping)

### 2) sessionStorage helpers
Create `src/lib/session.ts`:
- Keys:
  - `bsl:lastBook` (single)
  - `bsl:recentBooks` (array)
- Helpers:
  - `saveLastBook(book: BookSummary): void`
  - `loadLastBook(): BookSummary | null`
  - `pushRecentBook(book: BookSummary, limit = 5): BookSummary[]` (dedupe by docId)
  - `loadRecentBooks(): BookSummary[]`

Rules:
- Store JSON strings only.
- Wrap all reads/writes in try/catch; if storage fails, silently ignore.

### 3) Search results → Book detail navigation
In the search results UI (where the list of hits is rendered):
- Each item becomes a clickable link:
  - `to={/book/${docId}}`
  - `state={{ book: <BookSummary>, fromQuery: <q> }}` (state is optional but preferred)
- On click (or before navigation):
  - call `saveLastBook(bookSummary)`
  - call `pushRecentBook(bookSummary)`

Notes:
- If you’re using `<Link>`: attach `onClick`.
- If you’re using `navigate(...)`: do storage first, then navigate.

### 4) BookDetailPage: render from state or session
Update `src/pages/BookDetailPage.tsx`:
- Read `docId` from `useParams()`
- Try to get book data in this order:
  1) `const stateBook = (location.state as any)?.book`
  2) `const lastBook = loadLastBook()` (ensure docId matches)
  3) `const recentBooks = loadRecentBooks()` and pick matching docId

Render:
- Title + authors
- Publisher / year / volume / edition labels
- A “Back to search” button:
  - if state includes `fromQuery`, link to `/search?q=...`
  - else link to `/search`

Empty state:
- If no matching data is found, show:
  - “No cached book details for this item yet.”
  - Link back to Search.

### 5) Recently viewed section
On `BookDetailPage`, show a “Recently viewed” list (max 5):
- Each item links to `/book/:docId`
- Clicking one should also update `bsl:lastBook`.

Optional (nice): also show recently viewed on HomePage sidebar.

### 6) Styling (simple, consistent)
- Use Bootstrap card layout:
  - A main card for book details
  - A secondary card/list group for “Recently viewed”
- Keep responsive behavior: stack on mobile, split columns on desktop.

---

## Acceptance (Manual)

1) Run web-user:
```bash
cd apps/web_user
npm install
cp .env.example .env
npm run dev -- --port 5174
```

2) Go to `/search?q=해리` and run a search (per U-0107/U-0108).

3) Click a result:
- Navigates to `/book/b1` (or appropriate docId)
- Detail page shows title/authors/publisher/year

4) Refresh the detail page:
- Detail page still renders using sessionStorage fallback

5) Open another book:
- “Recently viewed” shows up to 5 items, newest first

---

## Deliverables
- List of created/changed files
- How to run locally
- Notes: this is session-only caching until a real Book Detail backend endpoint exists
