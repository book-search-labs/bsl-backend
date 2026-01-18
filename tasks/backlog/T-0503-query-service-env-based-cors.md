# T-0503 — Query Service: Env-based CORS (dev/staging/prod ready)

## Goal
Fix the browser preflight failure (`OPTIONS 405 Method Not Allowed`) by enabling **CORS** in **Query Service (FastAPI)**, using an **environment-variable allowlist** so it stays safe and maintainable across **local / staging / production**.

After this ticket:
- Browser requests from `web-admin` and `web-user` to `http://localhost:8001/query-context` succeed
- CORS origins are controlled via env vars (no hardcoded origins in code)
- Local dev has a sane default (Vite ports)

Non-goals:
- No auth/CSRF implementation
- No API versioning changes
- No changes to Search Service / Ranking Service

---

## Scope

### Allowed
- `services/query-service/app/main.py`
- `services/query-service/.env.example` (or `services/query-service/.env.local.example` if that’s your convention)
- `docs/RUNBOOK.md` (optional: add a short section on env-based CORS)

### Forbidden
- `services/search-service/**`
- `services/ranking-service/**`
- `infra/**`
- `db/**`

---

## Background
Your browser is sending a **preflight** request:
- `OPTIONS http://localhost:8001/query-context`

FastAPI returns `405` unless CORS middleware handles it. Adding **Starlette CORS middleware** is the normal solution.

---

## Implementation Requirements

### 1) Add CORS middleware in `app/main.py`
Update `services/query-service/app/main.py` to:
- Read allowed origins from env
- Add `CORSMiddleware`
- Support credentials and common headers

**Env variables** (comma-separated):
- `CORS_ALLOW_ORIGINS` (primary)
- Optional convenience flags:
  - `CORS_ALLOW_ORIGIN_REGEX` (if you want regex-based allow; optional)

**Defaults (local dev only):**
If `CORS_ALLOW_ORIGINS` is not set, default to these origins:
- `http://localhost:5173` (Vite default)
- `http://localhost:5174` (common 2nd Vite app)
- `http://localhost:4173` (Vite preview)

**Middleware settings (recommended):**
- `allow_origins`: parsed list (trim whitespace; ignore empty)
- `allow_credentials`: `true`
- `allow_methods`: `["*"]`
- `allow_headers`: `["*"]`
- `expose_headers`: include `x-trace-id`, `x-request-id` (helpful for debugging)

### 2) Add `.env.example` for Query Service
Create (or update) `services/query-service/.env.example`:

```env
# Query Service
PORT=8001

# CORS: comma-separated list of allowed web origins.
# Local defaults are applied if this is not set.
CORS_ALLOW_ORIGINS=http://localhost:5173,http://localhost:5174,http://localhost:4173

# Optional: regex allowlist (use carefully in prod)
# CORS_ALLOW_ORIGIN_REGEX=
```

**Do not commit a real `.env`.** Ensure `.env` is ignored (repo root `.gitignore` or service `.gitignore`).

### 3) Keep the FastAPI app wiring intact
Your current main is:

```py
from fastapi import FastAPI
from app.api.routes import router as api_router

app = FastAPI(title="query-service")
app.include_router(api_router)
```

After the ticket, it should still mount routes exactly the same—just with CORS added.

---

## Suggested Code (what Codex should implement)
In `services/query-service/app/main.py`:
- import `os`
- import `CORSMiddleware`
- parse `CORS_ALLOW_ORIGINS`

Example logic (high-level):
- `raw = os.getenv("CORS_ALLOW_ORIGINS", "")`
- `origins = [o.strip() for o in raw.split(",") if o.strip()]`
- if empty -> set local defaults
- apply `CORSMiddleware`

---

## Acceptance Tests

### 1) Run Query Service
```bash
cd services/query-service
uvicorn app.main:app --reload --port 8001
```

### 2) Verify preflight succeeds
From another terminal:
```bash
curl -i -X OPTIONS 'http://localhost:8001/query-context' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
```

✅ Expected:
- `HTTP/1.1 200` or `204`
- Response contains `access-control-allow-origin: http://localhost:5173`

### 3) Verify POST works from browser
From `web-admin` or `web-user` running on Vite:
- call `POST http://localhost:8001/query-context`
- confirm Network tab shows no CORS error

---

## Output (in dev summary)
- Files changed
- How to configure CORS in local vs staging/prod
- Curl preflight command + expected headers
