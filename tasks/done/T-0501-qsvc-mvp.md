# T-0501 — Query Service MVP: /health, /query-context (FastAPI) [DETAILED]

## Goal
Implement an MVP **Query Service (QS)** in FastAPI.

Deliverables:
- `GET /health` returns `{"status":"ok"}`
- `POST /query-context` returns **QueryContext v1** that conforms to:
  - `contracts/query-context.schema.json`
- Add **>= 2 unit tests** and document how to run.

Non-goals:
- No ML, no external calls, no integration with Search Service in this ticket.

---

## Must Read (SSOT)
- `AGENTS.md`
- `docs/API_SURFACE.md`
- `contracts/query-context.schema.json`
- `contracts/examples/query-context.sample.json`
- `data-model/normalization-rules.md` (follow it)

---

## Scope

### Allowed
- `services/query-service/**`
- (Optional) `docs/RUNBOOK.md` (only add QS run commands)
- (Optional) `scripts/test.sh` (only if you want to run QS tests there)

### Forbidden
- `contracts/**`
- `infra/**`
- `db/**`
- `services/search-service/**`

---

## Service Spec

### Local Dev Defaults
- Host: `0.0.0.0`
- Port: `8001`
- Base URL: `http://localhost:8001`

### Endpoints

#### 1) GET `/health`
Response:
- HTTP 200
```json
{ "status": "ok" }
