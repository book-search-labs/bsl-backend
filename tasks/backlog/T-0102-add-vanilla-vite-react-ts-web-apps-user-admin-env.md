# T-0102 — Add Vanilla Vite (React + TS) Web Apps (User + Admin) + .env

## Goal
Add **two** minimal, vanilla Vite (React + TypeScript) web apps to this repository:

- `apps/web-user/` (end-user facing)
- `apps/web-admin/` (admin console)

Both apps must be:
- Vite + React + TS (no extra frameworks)
- `.env.example` + `.env` support (documented; **do not commit real secrets**)
- A tiny working UI that proves env wiring (renders env values on screen)

This ticket is intentionally **minimal** (no routing, no state libs, no UI kits, no testing required).

---

## Must Read (SSOT)
- `AGENTS.md` (repo rules)
- `docs/RUNBOOK.md` (update only if needed)

---

## Scope

### Allowed
- `apps/web-user/**`
- `apps/web-admin/**`
- `docs/RUNBOOK.md` (optional: add short run instructions)

### Forbidden
- `services/**`
- `infra/**`
- `contracts/**`
- `db/**`

---

## Repository Placement
Create / use this structure:

```
apps/
  web-user/
  web-admin/
```

If `apps/` does not exist, create it.

---

## Implementation Requirements

## 1) Create Vite React+TS apps
Create two Vite projects (React + TypeScript):

### A) User app
Path: `apps/web-user/`

Expected files (typical Vite structure):
- `apps/web-user/package.json`
- `apps/web-user/vite.config.ts`
- `apps/web-user/tsconfig.json`
- `apps/web-user/index.html`
- `apps/web-user/src/main.tsx`
- `apps/web-user/src/App.tsx`

### B) Admin app
Path: `apps/web-admin/`

Expected files (typical Vite structure):
- `apps/web-admin/package.json`
- `apps/web-admin/vite.config.ts`
- `apps/web-admin/tsconfig.json`
- `apps/web-admin/index.html`
- `apps/web-admin/src/main.tsx`
- `apps/web-admin/src/App.tsx`

Constraints:
- Keep dependencies minimal (**only what Vite template generates**).
- No styling frameworks required; plain CSS is fine.
- Keep React rendering basic (no extra libraries).

---

## 2) .env wiring (Vite convention)
Create **per-app** env example files:

- `apps/web-user/.env.example`
- `apps/web-admin/.env.example`

Document/ensure:
- Vite only exposes env vars prefixed with `VITE_`.
- Local developers can copy `.env.example` to `.env`.

### Required keys

#### `apps/web-user/.env.example`
Must include at least:
- `VITE_QUERY_BASE_URL=http://localhost:8001`
- `VITE_SEARCH_BASE_URL=http://localhost:8080`

#### `apps/web-admin/.env.example`
Must include at least:
- `VITE_QUERY_BASE_URL=http://localhost:8001`
- `VITE_SEARCH_BASE_URL=http://localhost:8080`

Also ensure:
- `.env` is ignored by git (either per-app `.gitignore` or root `.gitignore`):
  - `apps/web-user/.env`
  - `apps/web-admin/.env`

---

## 3) Minimal UI to prove env works
In **both** apps (`App.tsx`):
- Render a title:
  - User: `BSL Web User (Vite + React + TS)`
  - Admin: `BSL Web Admin (Vite + React + TS)`
- Render env values:
  - `import.meta.env.VITE_QUERY_BASE_URL`
  - `import.meta.env.VITE_SEARCH_BASE_URL`
- Show a simple status:
  - “Env loaded ✅” if both are present
  - “Missing env ❌” otherwise

Implementation hint:
- Show env values in a `<pre>` block for clarity.

Optional (still minimal):
- A text input + button that only echoes the input (no API calls in this ticket).

---

## 4) Run instructions
Add README per app (preferred):
- `apps/web-user/README.md`
- `apps/web-admin/README.md`

Each README must include copy-paste commands:

### User app
```bash
cd apps/web-user
npm install
cp .env.example .env
npm run dev -- --port 5173
```

### Admin app
```bash
cd apps/web-admin
npm install
cp .env.example .env
npm run dev -- --port 5174
```

Also include build/preview commands (both apps):
```bash
npm run build
npm run preview -- --port <PORT>
```

Optionally, append a short section to `docs/RUNBOOK.md` linking to these READMEs (keep it short).

---

## Acceptance Tests (What to run)

### 1) User app
```bash
cd apps/web-user
npm install
cp .env.example .env
npm run dev -- --port 5173
```
Open:
- http://localhost:5173

✅ Done when:
- Page loads
- App renders env values (or clearly indicates missing env)

### 2) Admin app
```bash
cd apps/web-admin
npm install
cp .env.example .env
npm run dev -- --port 5174
```
Open:
- http://localhost:5174

✅ Done when:
- Page loads
- App renders env values (or clearly indicates missing env)

### 3) Git hygiene
✅ Done when:
- Repo does **not** include committed `.env` files with real secrets.

---

## Output (in dev summary)
- Created/updated file list
- How to run (copy-paste)
- Any known issues
