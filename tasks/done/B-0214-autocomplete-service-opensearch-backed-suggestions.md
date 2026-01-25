# B-0214 — Autocomplete Service: OpenSearch-backed suggestions (ac_suggest_read)

## Goal
Upgrade **Autocomplete Service** so it returns **real typeahead suggestions** from **OpenSearch** using the aliases seeded in **B-0211**.

**Flow**
`Web (User/Admin) → Autocomplete Service → OpenSearch → suggestions[]`

After this ticket:
- `GET /v1/autocomplete` returns suggestions from OpenSearch `ac_suggest_read`
- Results are stable, fast, and safe (timeouts, min query length)
- CORS is enabled for local dev (web-admin :5173, web-user :5174)

Non-goals:
- No ML ranking / personalization
- No Kafka logging
- No new OpenSearch index migrations (B-0211 remains SSOT for index/alias names)

---

## Must Read (SSOT)
- `AGENTS.md`
- B-0211 notes / runbook: alias names for autocomplete indices
- Existing Autocomplete Service code & API spec from **B-0213**

---

## Scope

### Allowed
- `services/autocomplete-service/**`
- `docs/RUNBOOK.md` (optional: add 2 curl examples)

### Forbidden
- `services/search-service/**`
- `services/query-service/**`
- `apps/**`
- `contracts/**`
- `infra/**`
- `db/**`

---

## API

### Endpoint
- `GET /v1/autocomplete`

### Query params
- `q` (required): user input string
- `size` (optional): number of suggestions (default 10, max 20)

### Headers
- Read (if present):
  - `x-trace-id`
  - `x-request-id`
- If missing, generate.

### Response (shape must match web-user U-0112)
```json
{
  "trace_id": "trace_demo",
  "request_id": "req_demo",
  "took_ms": 12,
  "suggestions": [
    { "text": "해리 포터", "score": 3.14, "source": "opensearch", "type": "TITLE" }
  ]
}
```

### Errors
- `400` if `q` missing/blank or shorter than min length
- `503` if OpenSearch unavailable

---

## OpenSearch integration

### Index/Alias
Use the **read alias** (from B-0211):
- `ac_suggest_read`

> If your alias differs, do not invent a new one — use the existing alias defined by B-0211 in your repo.

### Query strategy (MVP)
Use a **prefix-friendly** search:

- Minimum query length: `2` (Hangul/Latin 모두)
- Normalize query (MVP): `trim()` + collapse whitespace

OpenSearch query (example):
- `size = <size>`
- `track_total_hits = false`
- Sort by `_score desc`

Suggested query DSL (keep simple):
```json
{
  "size": 10,
  "query": {
    "bool": {
      "should": [
        { "match_phrase_prefix": { "text": { "query": "해리", "slop": 0, "max_expansions": 50 } } },
        { "prefix": { "text.keyword": "해리" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

### Response mapping
From each hit, map:
- `text`: `_source.text` (fallback to `_source.term` if your schema uses `term`)
- `type`: `_source.type` (optional)
- `score`: `_score` (optional)
- `source`: constant string `"opensearch"`

Deduplicate by `text` (case/whitespace-normalized) and keep top `size`.

### Timeouts & safety
- OpenSearch request timeout: 200ms (configurable)
- If OpenSearch times out/unavailable:
  - return `503` with `{ error: { code, message }, trace_id, request_id }`

---

## Local dev configuration

### Port
Fix Autocomplete Service port to **8081** for local dev.
- `SERVER_PORT=8081` (Spring)
- or `PORT=8081` (Node/FastAPI), whichever your service uses

### Env vars
Add (or ensure) these exist:
- `AUTOCOMPLETE_OPENSEARCH_BASE_URL=http://localhost:9200`
- `AUTOCOMPLETE_OPENSEARCH_INDEX_ALIAS=ac_suggest_read`
- `AUTOCOMPLETE_REQUEST_TIMEOUT_MS=200`
- `AUTOCOMPLETE_MIN_QUERY_LEN=2`

### CORS
Allow (dev-only):
- `http://localhost:5173` (web-admin)
- `http://localhost:5174` (web-user)

---

## Acceptance Tests

### Pre-req
- OpenSearch running locally
- B-0211 already applied so `ac_suggest_read` exists

Verify alias:
```bash
curl -s "http://localhost:9200/_cat/aliases?v" | grep ac_
```

### Run Autocomplete Service
(Use your project’s standard command.) Example:
```bash
cd services/autocomplete-service
./gradlew bootRun
# or
npm run dev
# or
uvicorn app.main:app --reload --port 8081
```

### Curl
```bash
curl -s "http://localhost:8081/v1/autocomplete?q=해리&size=5" | jq .
```

✅ Done when:
- Response has `suggestions[]` with non-empty `text`
- `took_ms` is present
- `trace_id` / `request_id` always present
- `q` missing → `400`
- OpenSearch down → `503`

---

## Output (Dev Summary)
- Changed files list
- How to run Autocomplete Service locally (port 8081)
- One curl example and expected output
