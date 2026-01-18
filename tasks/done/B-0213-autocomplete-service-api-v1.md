# B-0213 — Autocomplete Service: API v1 (OpenSearch-backed)

## Goal
Implement the **Autocomplete Service** so it exposes a production-shaped (but MVP) HTTP API:

`Web (Admin/User) → Autocomplete Service (/autocomplete) → OpenSearch (ac_* aliases) → Suggestions`

After this ticket:
- Autocomplete Service runs locally on a **fixed port** and serves `GET /autocomplete`.
- It queries OpenSearch **autocomplete indices via aliases** (created in **B-0211**) and returns merged suggestions.
- It returns stable JSON with `trace_id`, `request_id`, `took_ms`, and `suggestions[]`.
- CORS allows local dev origins:
  - `http://localhost:5173` (web-admin)
  - `http://localhost:5174` (web-user)

Non-goals:
- No Redis hot-prefix cache yet
- No click/impression logging yet
- No personalization yet
- No fuzzy spell/autocorrect here

---

## Must Read (SSOT)
- `AGENTS.md`
- `tasks/done/B-0211-...` (alias + seed for autocomplete indices)

---

## Scope

### Allowed
- `services/autocomplete-service/**`
- `docs/RUNBOOK.md` (optional: add one short curl snippet)

### Forbidden
- `services/search-service/**`
- `services/query-service/**`
- `services/ranking-service/**`
- `infra/**`
- `db/**`
- `contracts/**` (do **not** add schema files in this ticket)

---

## Port / Local Runtime

### Port (fixed)
- **autocomplete-service: 8081**

(Keep existing Search Service on 8080.)

---

## OpenSearch Dependencies

This ticket assumes **B-0211** already created autocomplete indices + aliases.

Expected aliases (examples — adjust if your repo uses different names):
- `ac_authors_read` → points to the current authors autocomplete index
- `ac_series_read` → points to the current series autocomplete index

If your aliases are named differently, define them as properties and keep code alias-driven.

---

## API Spec

### Endpoint
`GET /autocomplete`

### Query params
- `q` (string, required) — user input
- `size` (int, optional, default `10`, clamp `1..20`) — max suggestions

### Headers (optional)
- `x-trace-id`
- `x-request-id`

If headers are missing, generate values (UUID-based is OK).

### Response (JSON)
```json
{
  "trace_id": "trace_demo",
  "request_id": "req_demo",
  "took_ms": 12,
  "suggestions": [
    { "text": "해리 포터", "score": 12.3, "source": "series" },
    { "text": "J.K. 롤링", "score": 10.1, "source": "author" }
  ]
}
```

### Error response (JSON)
- `400` when `q` is missing/blank
- `503` when OpenSearch is unavailable

```json
{
  "error": { "code": "invalid_request", "message": "q is required" },
  "trace_id": "...",
  "request_id": "..."
}
```

---

## Implementation Requirements

### 1) Controller
Create a controller that:
- Validates `q`
- Clamps `size`
- Calls a service layer that fetches suggestions
- Returns the response envelope above

### 2) OpenSearch Gateway
Add an OpenSearch client/gateway dedicated to Autocomplete.

Configuration (env/properties):
- `OPENSEARCH_URL` (default `http://localhost:9200`)
- `OPENSEARCH_USERNAME` / `OPENSEARCH_PASSWORD` (optional)
- `AC_AUTHORS_ALIAS` (default `ac_authors_read`)
- `AC_SERIES_ALIAS` (default `ac_series_read`)

### 3) Query strategy (MVP)
For `q`:
- Query **authors alias** and **series alias** (in parallel is nice-to-have)
- Use a prefix-friendly approach:
  - If indices are modeled with `search_as_you_type`, use `multi_match` on that field family
  - If indices are modeled with `completion` suggester, use `suggest`

**MVP acceptable:** implement one approach that matches your current index mapping.

Return a merged list:
- Combine results from authors + series
- Normalize to `{text, score, source}`
- Deduplicate by `text` (keep higher score)
- Sort by `score desc`
- Trim to `size`

### 4) CORS
Allow local dev origins:
- `http://localhost:5173`
- `http://localhost:5174`

### 5) Timeouts
Add a conservative timeout for OpenSearch calls (e.g., 150–300ms) so UI doesn’t hang.

### 6) Logging
Log one line per request:
- trace_id, request_id, q length, size, took_ms

---

## Acceptance Tests

### A) Ensure OpenSearch aliases exist
```bash
curl -s "http://localhost:9200/_cat/aliases?v" | egrep "ac_|authors|series"
```

### B) Run Autocomplete Service
```bash
cd services/autocomplete-service
./gradlew bootRun
# or whatever your service uses (mvn / docker / etc.)
```

### C) Curl
```bash
curl -s "http://localhost:8081/autocomplete?q=해리&size=10" \
  -H 'x-trace-id: trace_demo' \
  -H 'x-request-id: req_demo' | jq .
```

✅ Done when:
- `suggestions` is a non-empty array for common prefixes (e.g., 해리)
- `trace_id` / `request_id` echo back (or are generated)
- Service returns `400` when `q` is missing/blank

---

## Dev Notes
- Keep DTOs very small (avoid over-modeling the OS response).
- If your OpenSearch mapping differs from assumptions, adapt queries to your actual fields.
- Don’t touch Search Service in this ticket (that was the earlier mistake).
