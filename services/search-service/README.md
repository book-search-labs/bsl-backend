# Search Service

Search Service is the online retrieval/ranking orchestrator for BSL.

## What it does
- Runs lexical + vector retrieval and fuses candidates (RRF/weighted fusion).
- Calls Ranking Service for rerank when enabled.
- Applies fallback/degrade policies (vector off, rerank off) under timeout/error conditions.
- Runs a single enhance retry (`/query/enhance`) only for low-quality results (zero/low results).
- Exposes debug payloads (query DSL, stage timings, fallback/enhance decisions).

## Main APIs
- `POST /search` - Hybrid search endpoint.
- `GET /books/{docId}` - Document detail lookup.
- `GET /health` - Liveness.

## Query flow (qc.v1.1)
1. Receive `query_context_v1_1` from BFF.
2. Build execution plan from `retrievalHints`.
3. Retrieve lexical/vector candidates and fuse.
4. If quality is poor, call QS `/query/enhance` and retry once.
5. Rerank (optional), then return hits + debug.

## Degrade and protection
- Vector/rerank circuit breakers.
- Stage time budgets and timeout caps.
- SERP cache + book detail cache.
- Fallback policies from QueryContext (`fallbackPolicy`).

## Local run
```bash
cd /path/to/bsl-backend
./gradlew :services:search-service:bootRun
```

Default port: `18087` (override with `SEARCH_PORT`).

## Key config
- OpenSearch: `OPENSEARCH_URL`, `OPENSEARCH_DOC_INDEX`, `OPENSEARCH_VEC_INDEX`
- Query Service enhance: `QUERY_BASE_URL`, `QUERY_TIMEOUT_MS`
- Ranking: `RANKING_BASE_URL`, `RANKING_TIMEOUT_MS`
- Quality gate: `SEARCH_QUALITY_LOW_RESULTS_HITS_THRESHOLD`, `SEARCH_QUALITY_LOW_RESULTS_TOP_SCORE_THRESHOLD`
- Caches: `SEARCH_SERP_CACHE_*`, `SEARCH_BOOK_CACHE_*`
