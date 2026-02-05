# T-0802 — Search Service: Accept QueryContext (qc.v1.1) and execute plan (lex/vector/rerank, filters, fallbacks)

## Goal
Upgrade **Search Service (Spring Boot)** so `POST /search` can accept the **final QueryContext v1.1** request shape (`meta.schemaVersion = "qc.v1.1"`) and drive execution using:

- `query.final` + `retrievalHints.queryTextSource`
- `retrievalHints.lexical / vector / rerank` settings
- `retrievalHints.filters[]` (slot-derived constraints)
- `retrievalHints.fallbackPolicy[]` (timeouts/errors/zero-results fallbacks)
- Deterministic ID propagation (`meta.traceId`, `meta.requestId`) end-to-end

This ticket implements a **minimal-but-correct subset** of qc.v1.1 while keeping:
- Legacy MVP request support (query.raw + options)
- QueryContext(v1) support from **T-0801** (if present)

---

## Must Read (SSOT)
- `AGENTS.md`
- `docs/API_SURFACE.md`
- Your latest **qc.v1.1 QueryContext example** (project SSOT)
- OpenSearch aliases (infra):
  - `books_doc_read`, `books_vec_read`
- (Optional) `docs/ARCHITECTURE.md` or `docs/INDEXING.md` (if present)

---

## Scope

### Allowed
- `services/search-service/**`
- `docs/RUNBOOK.md` (only add a short usage snippet if needed)
- `scripts/test.sh` (only if you add a Search Service test entry)

### Forbidden
- `contracts/**`
- `infra/**`
- `db/**`
- `services/query-service/**`
- `services/ranking-service/**` *(Search Service may CALL it, but do not modify it)*

---

## Preconditions (what must exist before running this ticket)

### Local infra
- OpenSearch running with doc/vec aliases from **T-0210**:
  - `books_doc_read` points to a seeded doc index with `title_ko`, `authors`, `volume`, `edition_labels`, etc.
  - `books_vec_read` points to a seeded vec index with `embedding` vectors
- Confirm quickly:
```bash
./scripts/local_up.sh
curl -s http://localhost:9200/_cat/aliases?v | grep books_
```

### Services
- Search Service already runs locally (from T-0602/T-0702):
  - `POST http://localhost:8080/search` works for legacy payload
- Ranking Service (optional for rerank stage):
  - `POST http://localhost:8082/rerank` works (from T-0701)
- Query Service (optional to produce qc.v1.1 live):
  - `POST http://localhost:8001/query-context` returns qc.v1.1 (from T-0502)

---

## API: Backward compatible request shapes

Search Service must accept **all** of these request shapes:

### A) Legacy MVP request (already supported)
```json
{
  "query": { "raw": "해리" },
  "options": { "size": 10, "from": 0, "enableVector": true, "rrfK": 60 }
}
```

### B) QueryContext(v1) request (T-0801)
```json
{
  "query_context": { "version": "v1", "...": "..." },
  "options": { "size": 10, "from": 0 }
}
```

### C) QueryContext(v1.1) request (NEW)
```json
{
  "query_context_v1_1": { "meta": { "schemaVersion": "qc.v1.1" }, "...": "..." },
  "options": { "size": 10, "from": 0 }
}
```

**Priority if multiple are present:**
1) `query_context_v1_1`
2) `query_context`
3) legacy `query.raw`

---

## IDs: Deterministic propagation
### qc.v1.1
- Use:
  - `query_context_v1_1.meta.traceId`
  - `query_context_v1_1.meta.requestId`
- Response must echo these IDs exactly.

### v1
- Use:
  - `query_context.trace_id`
  - `query_context.request_id`

### legacy
- Use headers `x-trace-id` / `x-request-id` if present; else generate UUIDs.

---

## Behavior requirements (qc.v1.1 subset)

### 1) Choose query text via `retrievalHints.queryTextSource`
Read:
- `query_context_v1_1.retrievalHints.queryTextSource`

Support:
- `"query.final"`
- `"query.norm"`
- `"query.raw"`

Mapping:
- `query.final` → `query_context_v1_1.query.final`
- `query.norm`  → `query_context_v1_1.query.norm`
- `query.raw`   → `query_context_v1_1.query.raw`

Default if missing:
- `"query.final"` if present, else `"query.norm"`, else `"query.raw"`.

Validation:
- If chosen text is missing/blank → **400**.

### 2) Lexical stage (books_doc_read)
Read:
- `retrievalHints.lexical.enabled` (default true)
- `retrievalHints.lexical.topKHint` (default 300; clamp 50..1000)
- `retrievalHints.lexical.operator` (AND/OR; default AND)
- `retrievalHints.lexical.minimumShouldMatch` (optional)
- `retrievalHints.lexical.preferredLogicalFields` (list; map logical → ES fields)

Minimum logical → ES mapping:
- `title_ko` → `title_ko`
- `title_ko.edge` → `title_ko.edge`
- `author_ko` → `authors.name_ko`
- `series_ko` → `series_name`

Lexical query approach:
- `multi_match` across mapped fields (or a default set if list is empty)
- Always apply:
  - `must_not: { term: { is_hidden: true } }`  *(unless you intentionally allow hidden via a supported filter)*

### 3) Vector stage (books_vec_read)
Read:
- `retrievalHints.vector.enabled` (default true)
- `retrievalHints.vector.topKHint` (default 200; clamp 20..500)
- `retrievalHints.vector.fusionHint.method` (support only `"rrf"` in this ticket)

Vector query:
- Use OpenSearch `knn` query on `embedding`.
- **Deterministic query vector**:
  - Keep the same deterministic strategy already used in Search Service MVP (T-0602), so behavior is stable.

If vector errors/timeouts:
- Do not fail request; continue lexical-only and mark fallback.

### 4) Fusion (RRF)
Read:
- `retrievalHints.vector.fusionHint.k` (default 60; clamp 10..200)
- Ignore weightHint in this ticket (optional to implement; safe to ignore)

Implement:
- If both stages available → merge by RRF ranks.
- If one stage missing → use the available stage.
- Deterministic tie-break:
  - if scores equal → `doc_id` ascending.

Response `strategy`:
- `bm25_v1_1` (lexical-only)
- `hybrid_rrf_v1_1`
- `hybrid_rrf_v1_1_fallback_lexical`

### 5) Rerank stage (Ranking Service)
Read:
- `retrievalHints.rerank.enabled` (default false)
- `retrievalHints.rerank.topKHint` (default 50; clamp 10..200)

Behavior:
- If enabled:
  - Take top `topKHint` candidates post-fusion
  - Call Ranking Service `/rerank`
  - Reorder those candidates by returned rank/score
- If rerank fails/timeouts:
  - Return fused results without rerank
  - Mark fallback as applied if policy exists

### 6) Filters (slot-derived constraints)
Read:
- `retrievalHints.filters[]` array of objects containing `and: []` constraints

Support only these logical fields in this ticket:
- `volume` (CATALOG) → ES field `volume` (term)
- `edition_label` / `edition_labels` (CATALOG) → ES field `edition_labels` (terms)
- `isbn13` (CATALOG) → ES field `identifiers.isbn13` (term)
- `language_code` → ES field `language_code` (term)

Interpretation:
- Each filter item has an `and` array; translate supported constraints into ES `filter` clauses.
- Apply the same filters to:
  - lexical query (books_doc_read)
  - vector query (books_vec_read)  *(only if the field exists on vec index; safe if not)*

Unknown constraints:
- Ignore safely (do not fail).

### 7) Fallback policy (minimal)
Read:
- `retrievalHints.fallbackPolicy[]`

Support `when` conditions:
- `onTimeout`
- `onVectorError`
- `onRerankTimeout`
- `onRerankError`
- `onZeroResults`

Support `mutations`:
- `disable: ["vector", "rerank"]`
- `disable: ["rerank"]`
- `useQueryTextSource: "query.norm" | "query.final" | "query.raw"`
- `adjustHint.lexical.topK` (optional)

Rules:
- Apply fallbacks only when the triggering condition happens.
- Record applied fallback id in response debug.

### 8) Timeouts (best-effort)
Read:
- `retrievalHints.executionHint.timeoutMs` (default 120; clamp 50..500)
- (Optional) `budgetMs.lexical/vector/rerank`

Implementation guidance:
- If you can do per-request OpenSearch timeouts → use min(stage budget, overall timeout).
- Otherwise clamp client read timeout using overall timeout (best-effort).

---

## Response requirements
Keep existing Search Service response shape, plus:

For qc.v1.1:
- `strategy` must be `*_v1_1`
- `trace_id`, `request_id` must echo v1.1 meta ids
- `ranking_applied` boolean (already exists)

Add a minimal `debug` object (either always or when `options.debug=true` if you already have it):
```json
"debug": {
  "applied_fallback_id": "FB1_LEXICAL_ONLY",
  "query_text_source_used": "query.final",
  "stages": { "lexical": true, "vector": true, "rerank": false }
}
```

Do not break existing clients.

---

## Error handling
- Invalid JSON / missing body → 400
- Missing/blank chosen query text → 400
- OpenSearch unavailable → 503
- Unexpected error → 500

Error response shape (keep consistent):
```json
{ "error": { "code": "...", "message": "..." }, "trace_id": "...", "request_id": "..." }
```

---

## Implementation Notes (suggested structure)
- Controller: detect request kind:
  - contains `query_context_v1_1` (JsonNode) → v1.1 path
  - else contains `query_context` → v1 path
  - else legacy
- Introduce a small internal abstraction:
  - `ExecutionPlan` / `PlanContext` computed from input
  - unify into the existing pipeline (lex → vec → fuse → rerank)
- Keep qc.v1.1 parsing tolerant (ignore unknown keys).

---

## Testing Requirements (unit tests)
Must pass on a clean checkout with no OpenSearch requirement.

Add/extend MockMvc tests with mocked collaborators:

1) Accepts qc.v1.1 request and returns 200
2) qc.v1.1 missing chosen query text (per queryTextSource) → 400
3) ID propagation: response IDs match `meta.traceId` / `meta.requestId`
4) Filter mapping: when filters include volume=1 → query builder includes `term: { "volume": 1 }`
5) Fallback: simulate vector error → strategy becomes `hybrid_rrf_v1_1_fallback_lexical` and `debug.applied_fallback_id` set (when policy present)

Run:
```bash
cd services/search-service
./gradlew test
```

---

## Manual Validation (copy-paste)

### 1) Start OpenSearch
```bash
./scripts/local_up.sh
curl -s http://localhost:9200/_cat/aliases?v | grep books_
```

### 2) Run Ranking Service (optional for rerank)
```bash
cd services/ranking-service
./gradlew bootRun
# should listen on :8082
```

### 3) Run Search Service
```bash
cd services/search-service
./gradlew bootRun
# should listen on :8080
```

### 4) Call /search with qc.v1.1 payload (minimal)
```bash
curl -s -XPOST http://localhost:8080/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query_context_v1_1": {
      "meta": { "schemaVersion": "qc.v1.1", "traceId": "trace_demo", "requestId": "req_demo", "tenantId": "books", "timestampMs": 1768040000000, "locale": "ko-KR", "timezone": "Asia/Seoul" },
      "query": { "raw": "해리-포터 01권", "norm": "해리 포터 1권", "final": "해리포터 1권" },
      "retrievalHints": {
        "queryTextSource": "query.final",
        "lexical": { "enabled": true, "topKHint": 300, "operator": "and", "preferredLogicalFields": ["title_ko", "author_ko"] },
        "vector": { "enabled": true, "topKHint": 200, "fusionHint": { "method": "rrf", "k": 60 } },
        "rerank": { "enabled": true, "topKHint": 50, "rerankModelHint": "toy_rerank_v1" },
        "filters": [
          { "and": [ { "scope": "CATALOG", "logicalField": "volume", "op": "eq", "value": 1, "strict": false, "reason": "SLOT_VOLUME" } ] }
        ],
        "fallbackPolicy": [
          { "id": "FB1_LEXICAL_ONLY", "when": { "onTimeout": true, "onVectorError": true }, "mutations": { "disable": ["vector", "rerank"], "useQueryTextSource": "query.norm" } }
        ],
        "executionHint": { "timeoutMs": 120 }
      }
    },
    "options": { "size": 5, "from": 0 }
  }'
```

Expected:
- `trace_id == trace_demo`, `request_id == req_demo`
- `strategy` starts with `hybrid_rrf_v1_1` (or fallback variant)
- `hits.length >= 1`
- If rerank enabled and Ranking Service is running → `ranking_applied=true`

---

## Output (in dev summary)
- List changed files
- How to run unit tests
- Curl examples for legacy / v1 / v1.1 request shapes
- Known limitations / TODOs (subset of filters, deterministic demo vector)
