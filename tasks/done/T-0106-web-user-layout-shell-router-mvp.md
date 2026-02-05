# T-0106 — Web User: Layout Shell + Router (MVP)

## Goal
Create the **minimum usable app shell** for **Web User** (Vite + React + TS) with:
- a stable **layout frame** (top nav + content area)
- **React Router** routes for core pages
- a small **design system baseline** (Bootstrap + React-Bootstrap)
- **.env** wiring (Vite `VITE_*`) and a tiny “env loaded” indicator

This ticket intentionally does **not** implement real API calls yet (that’s the next ticket).

---

## Must Read (SSOT)
- `AGENTS.md`
- `docs/RUNBOOK.md` (update only if needed)

---

## Scope

### Allowed
- `apps/web-user/**`
- `docs/RUNBOOK.md` (only to add run instructions if missing)

### Forbidden
- `services/**`
- `contracts/**`
- `infra/**`
- `db/**`

---

## Repository Placement
App lives at:
- `apps/web-user/`

If `apps/` doesn’t exist, create it.

---

## Prerequisites (what should already exist)
- `apps/web-user` was created by **T-0102 (B plan)** (or you can create it in this ticket if not present).
- Node.js LTS installed locally.

---

## Implementation Requirements

### 1) Ensure Vite React+TS app exists
If not already present, create a Vite React+TS app at `apps/web-user/`.

Keep dependencies minimal:
- `react`, `react-dom`
- `react-router-dom`
- `bootstrap`, `react-bootstrap`, `bootstrap-icons`

> If the template already exists, keep it and modify only what you need.

---

### 2) .env wiring
Create / ensure:
- `apps/web-user/.env.example`
- `apps/web-user/.gitignore` ignores `.env` (or root `.gitignore`)

`.env.example` must include:
- `VITE_QUERY_SERVICE_BASE_URL=http://localhost:8001`
- `VITE_SEARCH_SERVICE_BASE_URL=http://localhost:8080`

---

### 3) App routing (React Router)
Use `react-router-dom` and create these routes:

- `/` → Home page (simple hero + links)
- `/search` → Search page (placeholder UI; no API yet)
- `/book/:docId` → Book detail page (placeholder)
- `/dev/env` → Env debug page (shows env values)
- `*` → NotFound page

Suggested file structure:
- `apps/web-user/src/app/App.tsx`
- `apps/web-user/src/app/router.tsx`
- `apps/web-user/src/layouts/MainLayout.tsx`
- `apps/web-user/src/pages/HomePage.tsx`
- `apps/web-user/src/pages/SearchPage.tsx`
- `apps/web-user/src/pages/BookDetailPage.tsx`
- `apps/web-user/src/pages/EnvDebugPage.tsx`
- `apps/web-user/src/pages/NotFoundPage.tsx`

---

### 4) Layout shell (Top Nav)
Implement a simple top navigation bar with:
- Brand: `BSL`
- Links: Home, Search, Env
- Right side: placeholder “Login” button (no auth logic)

Use Bootstrap/React-Bootstrap:
- Import Bootstrap CSS once (in `main.tsx`)

Layout behavior:
- Nav is fixed at top or static (either is fine)
- Content container has comfortable padding and max width (e.g., Bootstrap Container)

---

### 5) Search page placeholder (no API yet)
`/search` page should include:
- a query input box
- a Search button
- a placeholder results section (empty state)
- optional: show “Coming next ticket: call Query Service + Search Service”

Do **not** add fetch logic here yet.

---

### 6) Env debug page
`/dev/env` must render:
- `import.meta.env.VITE_QUERY_SERVICE_BASE_URL`
- `import.meta.env.VITE_SEARCH_SERVICE_BASE_URL`

And show:
- `Env loaded ✅` if both are non-empty, else `Missing env ❌`

---

### 7) README / run instructions
Create `apps/web-user/README.md` with copy-paste commands:

```bash
cd apps/web-user
npm install
cp .env.example .env
npm run dev -- --port 5174
```

Also include build/preview:
```bash
npm run build
npm run preview -- --port 5174
```

> Use port **5174** for web-user to avoid colliding with admin (often 5173).

---

## Acceptance Tests (What to run)

```bash
cd apps/web-user
npm install
cp .env.example .env
npm run dev -- --port 5174
```

Open:
- http://localhost:5174

✅ Done when:
- App loads without console errors
- Nav links work
- `/dev/env` shows env values or missing state
- `.env` is not committed

---

## Output (in dev summary)
- Created/updated file list
- How to run (copy-paste)
- Notes on next ticket (E2E Search API wiring)
