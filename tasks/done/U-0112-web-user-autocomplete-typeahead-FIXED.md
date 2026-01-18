# U-0112 — Web User: Autocomplete Typeahead (uses **Autocomplete Service**, not Search Service)

## Goal
Add a real-time **typeahead autocomplete** UX to **web-user** that calls the **Autocomplete Service** endpoint and shows suggestions under the global search bar.

After this ticket:
- As the user types in the global search input (AppShell), web-user calls **Autocomplete Service**
- A suggestion dropdown appears (keyboard + mouse friendly)
- Clicking a suggestion navigates to `/search?q=<suggestion>`
- Pressing **Enter** still navigates to `/search?q=<current input>`

Non-goals:
- No Search Service calls from autocomplete UI
- No analytics
- No “smart ranking” (just show what API returns)

---

## Must Read (SSOT)
- `apps/web-user/.env.example`
- Existing `src/api/*` and `src/hooks/*` if already created

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
You should be able to run:
- **Autocomplete Service**: `http://localhost:8002/autocomplete` (recommended default; see Env section)
- Web-user: `http://localhost:5174`

> Note: If you choose a different Autocomplete port, only update `.env` (do NOT hardcode).

---

## Environment Variables
Update / ensure `apps/web-user/.env.example` includes:

```env
VITE_AUTOCOMPLETE_SERVICE_BASE_URL=http://localhost:8002
```

Rules:
- `.env` must be gitignored
- Do not commit a real `.env`

---

## API Contract (MVP)

### Endpoint
`GET {VITE_AUTOCOMPLETE_SERVICE_BASE_URL}/autocomplete?q=<query>&size=<n>`

### Response (example)
```json
{
  "trace_id": "t1",
  "request_id": "r1",
  "took_ms": 12,
  "suggestions": [
    { "text": "해리 포터", "score": 1.0, "source": "prefix" }
  ]
}
```

The UI only relies on:
- `suggestions[].text`

---

## Implementation Requirements

### 1) API client (web-user)
Create or fix the API client so it calls **Autocomplete Service** (NOT Search Service):

- `src/api/autocompleteService.ts`
  - Resolve base URL from:
    - `import.meta.env.VITE_AUTOCOMPLETE_SERVICE_BASE_URL`
    - fallback: `http://localhost:8002`
  - `fetchAutocomplete(query: string, size: number, signal?: AbortSignal)`
    - GET `/autocomplete?q=...&size=...`
    - Use `AbortController` for cancellation (caller-driven)

If you already have `fetchAutocomplete` but it points to Search Service env keys (`VITE_SEARCH_*`), **change it** to use `VITE_AUTOCOMPLETE_SERVICE_BASE_URL`.


### 2) Add typeahead dropdown to the global search bar
In `src/layouts/AppShell.tsx` (or wherever the global search input lives):

- Local state:
  - `query` (already exists)
  - `isOpen` (dropdown open/close)
  - `activeIndex` (keyboard navigation)
  - `suggestions` (array)
  - `loading`, `error` (optional)

- Debounce:
  - Use your existing `useDebouncedValue(query, 200~300)`

- Fetch behavior:
  - When debounced query length >= 1~2:
    - call `fetchAutocomplete(debouncedQuery, 8, signal)`
    - cancel in-flight request when query changes
  - If query becomes blank:
    - close dropdown + clear suggestions

- Open/close rules:
  - Open when suggestions are non-empty and input is focused
  - Close on:
    - outside click (`useOutsideClick`)
    - Escape key
    - navigation submit


### 3) Keyboard interactions
While dropdown is open:
- ArrowDown / ArrowUp changes `activeIndex`
- Enter:
  - if an item is active → navigate to `/search?q=<item.text>`
  - else → default submit behavior (existing)
- Escape closes dropdown


### 4) Mouse interactions
- Hover updates `activeIndex`
- Click suggestion navigates to `/search?q=<item.text>`


### 5) UI / styling (Bootstrap only)
- Use Bootstrap utilities (no new libraries)
- Suggested structure:
  - Wrap the input area in `position-relative`
  - Dropdown as `position-absolute w-100` below input
  - Each item styled like a list group:
    - `list-group`, `list-group-item`, `active`

- Ensure it behaves on mobile (touch):
  - Dropdown scroll if too tall (`max-height` + `overflow-auto`)


### 6) Error handling
If request fails:
- Don’t crash
- Either:
  - show a small muted “Autocomplete unavailable” row, **or**
  - just silently close dropdown


### 7) Run docs
Update `apps/web-user/README.md` (or create) to include:

```bash
cd apps/web-user
npm install
cp .env.example .env
npm run dev -- --port 5174
```

---

## Manual Validation

1) Start Autocomplete Service (example port 8002)
2) Start web-user:

```bash
cd apps/web-user
npm run dev -- --port 5174
```

3) Open `http://localhost:5174`
4) Type `해` then `해리`
   - Network tab should show requests to:
     - `http://localhost:8002/autocomplete?q=...`
   - Dropdown appears with suggestions
5) Click a suggestion
   - navigates to `/search?q=<suggestion>`
6) Arrow keys + Enter works
7) Escape / outside click closes dropdown

---

## Deliverables
- Summary of changed/created files
- How to run locally
- Confirmed that autocomplete calls **Autocomplete Service** base URL (env-driven)
