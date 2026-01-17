# T-0502 — Query Service: Emit QueryContext v1.1 (qc.v1.1) MVP

## Goal
Upgrade **Query Service (FastAPI)** so `POST /query-context` returns the **final QueryContext v1.1** shape (SSOT: `meta.schemaVersion = "qc.v1.1"`), in a **minimal-but-correct MVP** form that unblocks Search Service **T-0802**.

After this ticket:
- Query Service returns **qc.v1.1** payloads (single canonical output)
- `traceId` / `requestId` are propagated deterministically (headers → response)
- Query normalization produces:
  - `query.raw`, `query.nfkc`, `query.norm`, `query.nospace`, and `query.final`
  - a stable `query.canonicalKey` (best-effort MVP)
- `retrievalHints` is present with sane defaults:
  - `queryTextSource`, `lexical/vector/rerank` flags + topK hints
  - `executionHint.timeoutMs` and `cacheHint` placeholder
  - `filters` empty array (MVP) and `fallbackPolicy` minimal defaults
- Response remains JSON-only, stable keys, safe defaults

Non-goals:
- No DB changes
- No OpenSearch changes
- No “real” spell correction / LLM rewrite (still MVP)
- No new model serving dependency (embedding/rerank model hints are labels only)

---

## Must Read (SSOT)
- `AGENTS.md`
- Your latest QueryContext v1.1 example (qc.v1.1) in project notes
- `docs/RUNBOOK.md` (if present)

---

## Scope

### Allowed
- `services/query-service/**`
- `docs/RUNBOOK.md` (only if you add a short curl snippet)

### Forbidden
- `services/search-service/**`
- `services/ranking-service/**`
- `contracts/**` (do not add/update schema files in this ticket)
- `infra/**`
- `db/**`

---

## API

### Endpoint (keep)
- `POST /query-context`

### Headers
- Read (if present):
  - `x-trace-id`
  - `x-request-id`
- If missing, generate values.

### Request Body (keep minimal)
Accept the same request shape as current MVP:
```json
{
  "query": { "raw": "해리-포터 01권 리커버" },
  "client": { },
  "user": { }
}
```

### Response Body (NEW: qc.v1.1)
Return **only** qc.v1.1 (no v1 response).

---

## Implementation Requirements

### 1) Update response envelope to qc.v1.1
Replace current top-level keys:
- `version`, `trace_id`, `request_id`, ...

With:
- `meta` (schema + ids + runtime metadata)
- `query`, `detected`, `features`, `slots`, `understanding`, `spell`, `rewrite`, `retrievalHints`, `policy`, `executionTrace`, `debug`

**MVP: you may omit some optional sub-objects**, but the response must be structurally compatible with T-0802 expectations.

Minimum required top-level keys for this ticket:
- `meta`
- `query`
- `detected`
- `slots`
- `understanding`
- `spell`
- `rewrite`
- `retrievalHints`

Recommended to include (simple static placeholders are OK):
- `features`, `policy`, `executionTrace`, `debug`

---

### 2) `meta` mapping
Produce:
- `meta.schemaVersion = "qc.v1.1"`
- `meta.traceId`, `meta.requestId`
- `meta.tenantId = "books"` (or derive from env `BSL_TENANT_ID`, default "books")
- `meta.timestampMs = now()`
- `meta.locale = "ko-KR"` (env override OK)
- `meta.timezone = "Asia/Seoul"` (env override OK)

Pass-through:
- `meta.client` from request body `client` (if any)
- `meta.user` from request body `user` (if any)

Also include (static MVP allowed):
- `meta.compat.minSearchRequestVersion = "sr.v1.0"`
- `meta.compat.minRerankRequestVersion = "rr.v1.0"`

---

### 3) Query normalization outputs
Given `raw`:

Produce these fields:

- `query.raw`: request body value as-is
- `query.nfkc`: Unicode normalized (NFKC)
- `query.norm`: your existing `normalize_query(...)` output (whitespace/punct normalization)
- `query.nospace`: remove all spaces from `query.norm`
- `query.final`: **MVP rule**:
  - default = `query.norm` (or `query.nospace` if you want)
  - `query.finalSource = "norm"` (or `"rewrite"` if rewrite applied; MVP usually "norm")
- `query.tokens`: keep simple token list:
  - Either your existing `tokenize(query.norm)` as `[{t,pos,type,protected}]` (preferred)
  - OR output a simplified tokens array and keep `protectedSpans=[]` (MVP)

MVP canonical key:
- `query.canonicalKey`:
  - Build a stable string like:
    - `"{query.final}"` (minimum)
  - OR if you detect `N권` style volume and `리커버` edition:
    - `"해리포터|권:1|리커버"` style
  - If not implemented, set to `query.final`.

Also include:
- `query.normalized.rulesApplied`: list of strings (MVP can be empty or a minimal set)

---

### 4) Language detection
Reuse your existing `detect_language(...)` but map into:
```json
"detected": {
  "lang": { "primary": "ko", "confidence": 0.92 },
  "isMixed": false
}
```
MVP:
- If your detector returns `{detected, confidence}` already, map accordingly.

---

### 5) Slots (MVP minimal)
You may keep slots “empty” for now, but the object must exist:
```json
"slots": {
  "isbn": null,
  "volume": null,
  "edition": [],
  "set": { "value": false, "confidence": 1.0, "source": "mvp" },
  "chosung": { "value": false, "confidence": 1.0, "source": "mvp" }
}
```
Optional MVP improvement:
- Detect volume: regex like `(\d+)\s*권`
- Detect edition label: dictionary match for "리커버" -> value "recover"

---

### 6) Understanding (MVP)
Return something like:
```json
"understanding": {
  "intent": "WORK_LOOKUP",
  "confidence": 0.5,
  "method": "mvp",
  "entities": { "title": [], "author": [], "publisher": [], "series": [] },
  "constraints": { "preferredLogicalFields": ["title_ko", "series_ko", "author_ko"], "mustPreserve": [] }
}
```
MVP is fine as long as keys exist and types are stable.

---

### 7) Spell / Rewrite (MVP)
Keep as “not applied”:
- `spell.applied=false`
- `rewrite.applied=false` (or true if you implement the simple spacing rewrite; optional)

---

### 8) retrievalHints (MVP defaults that match your final design)
Emit:
```json
"retrievalHints": {
  "planId": "MVP_V1_1",
  "queryTextSource": "query.final",
  "lexical": {
    "enabled": true,
    "operator": "and",
    "topKHint": 300,
    "analyzerHint": "ko_search",
    "minimumShouldMatch": "2<75%",
    "preferredLogicalFields": ["title_ko", "series_ko", "author_ko"]
  },
  "vector": {
    "enabled": true,
    "topKHint": 200,
    "embedModelHint": "bge-m3-v1",
    "fusionHint": { "method": "rrf", "k": 60, "weightHint": { "lexical": 0.6, "vector": 0.4 } }
  },
  "rerank": {
    "enabled": false,
    "topKHint": 50,
    "rerankModelHint": "toy_rerank_v1",
    "featureHints": { "useVolumeSignal": true, "useEditionSignal": true }
  },
  "filters": [],
  "fallbackPolicy": [
    { "id": "FB1_LEXICAL_ONLY", "when": { "onTimeout": true, "onVectorError": true }, "mutations": { "disable": ["vector", "rerank"], "useQueryTextSource": "query.norm" } },
    { "id": "FB2_NO_RERANK", "when": { "onRerankTimeout": true, "onRerankError": true }, "mutations": { "disable": ["rerank"], "useQueryTextSource": "query.final" } }
  ],
  "executionHint": {
    "timeoutMs": 120,
    "budgetMs": { "lexical": 45, "vector": 45, "rerank": 25, "overhead": 5 },
    "concurrencyHint": { "maxFanout": 2, "strategy": "parallel_lex_vec" },
    "cacheHint": { "enabled": true, "cacheKey": "qc:books:mvp", "ttlSec": 120 }
  },
  "guardrails": {
    "maxLexicalTopK": 1000,
    "maxVectorTopK": 500,
    "maxRerankTopK": 200,
    "allowedFusionMethods": ["rrf", "weighted_sum"],
    "allowedEmbedModels": ["bge-m3-v1"],
    "allowedRerankModels": ["toy_rerank_v1", "minilm-cross-v2"]
  }
}
```

MVP notes:
- If you don’t want to support vector yet, you may set `vector.enabled=false` by default.
- CacheKey can be a stable derived string: e.g., hash of `query.canonicalKey` + `planId`.

---

## What you must have set up BEFORE running this ticket

### Repo / files expected to already exist
1) Query Service FastAPI app wiring:
- `services/query-service/app/api/routes.py` (or your current router file)
- `services/query-service/app/core/normalize.py` with:
  - `normalize_query(raw: str) -> str`
  - `tokenize(text: str) -> list[...]` (or list[str])
- `services/query-service/app/core/lid.py` with:
  - `detect_language(text: str) -> ...`

2) Run entrypoint:
- `services/query-service/app/main.py` (or equivalent) that mounts the router
- `services/query-service/requirements.txt` (or poetry/pyproject equivalent)

3) Local run docs (recommended):
- `docs/RUNBOOK.md` (optional, but helpful)

### Local environment
- Python 3.11+ recommended
- `pip`/`poetry` whichever the repo uses
- Port assumption:
  - Query Service on `http://localhost:8001`

### (Optional) Environment variables (can hardcode for MVP)
- `BSL_TENANT_ID` (default books)
- `BSL_LOCALE` (default ko-KR)
- `BSL_TIMEZONE` (default Asia/Seoul)

---

## Acceptance Tests (What to run)

### 1) Run Query Service
```bash
cd services/query-service
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

### 2) Curl: qc.v1.1 response
```bash
curl -s -XPOST http://localhost:8001/query-context \
  -H 'Content-Type: application/json' \
  -H 'x-trace-id: trace_demo' \
  -H 'x-request-id: req_demo' \
  -d '{ "query": { "raw": "해리-포터 01권 리커버" }, "client": {"device":"web"}, "user": {"userId":"u_1"} }' | jq .
```

✅ Done when:
- Response contains `meta.schemaVersion == "qc.v1.1"`
- Response contains `meta.traceId == "trace_demo"` and `meta.requestId == "req_demo"`
- Response contains `query.raw`, `query.norm`, `query.final`
- Response contains `retrievalHints.lexical.enabled`, `retrievalHints.vector.enabled`, `retrievalHints.executionHint.timeoutMs`
- Response is deterministic for the same input (except timestamps)

---

## Output (in dev summary)
- Changed files list
- How to run Query Service
- Curl example
- Notes on what is still MVP (slots/entities/rewrite)
