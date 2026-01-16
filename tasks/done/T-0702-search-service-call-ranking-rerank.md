# T-0702 — Search Service: call Ranking Service (/rerank) and apply rerank results

## Goal
Wire **Search Service (8080)** to call **Ranking Service (8082)** after hybrid retrieval (lexical + vector + RRF) and return results **reordered by rerank**.

After this ticket, a developer can:
1) start local OpenSearch (T-0210)
2) start Search Service (T-0602)
3) start Ranking Service (T-0701)
4) call `POST /search` and see results reranked via `POST /rerank`

Non-goals:
- No Query Service changes
- No OpenSearch mapping/infra changes
- No contracts/** changes (DTOs remain local to services)

---

## Must Read (SSOT)
- `AGENTS.md`
- `docs/RUNBOOK.md`
- `tasks/backlog/T-0602-search-service-hybrid-rrf-mvp.md`
- `tasks/backlog/T-0701-ranking-service-mvp-toy-rerank.md`

---

## Scope

### Allowed
- `services/search-service/**`
- `docs/RUNBOOK.md` (optional small update)
- `scripts/test.sh` (only if you must add an optional integration step)

### Forbidden
- `infra/**`
- `contracts/**`
- `db/**`
- `services/query-service/**`
- `services/ranking-service/**` (assume T-0701 already implemented)

---

## Environment Assumptions
- OpenSearch: `http://localhost:9200`
  - aliases exist: `books_doc_read`, `books_vec_read`
- Search Service: `http://localhost:8080`
- Ranking Service: `http://localhost:8082`
- Local dev: no auth

---

## Required Behavior

### 1) Search flow (updated)
Current (T-0602):
- lexical (books_doc_read) topK
- vector (books_vec_read) topK
- RRF merge
- hydrate from doc index
- return response with debug ranks

New (T-0702):
- Do **hybrid retrieval + RRF fusion** as before (keep existing behavior)
- Build **rerank request** using *fused candidates (pre-hydration is ok)*:
  - send top `rerankTopK` (default 50; configurable)
- Call Ranking Service `POST http://localhost:8082/rerank`
- Apply reranked ordering to final hits:
  - take top `options.size` after rerank
  - hydrate using doc index (if you haven’t hydrated yet)
- Response should include:
  - `strategy`: `"hybrid_rrf_rerank_v1"` when rerank applied
  - fallback to `"hybrid_rrf_v1"` when rerank disabled/fails

### 2) /search request (unchanged)
```json
{
  "query": { "raw": "해리" },
  "options": { "size": 10, "from": 0, "enableVector": true, "rrfK": 60 }
}
```

### 3) Ranking call — request shape
Call `/rerank` with:
```json
{
  "query": { "text": "<same as query.raw>" },
  "candidates": [
    {
      "doc_id": "b1",
      "features": {
        "lex_rank": 1,
        "vec_rank": 3,
        "rrf_score": 0.03226,
        "issued_year": 1999,
        "volume": 1,
        "edition_labels": ["recover"]
      }
    }
  ],
  "options": { "size": 50 }
}
```

**How to fill features**
- `lex_rank`: rank in lexical list (1-based), else null
- `vec_rank`: rank in vector list (1-based), else null
- `rrf_score`: the fused RRF score you computed in T-0602
- `issued_year`, `volume`, `edition_labels`:
  - Prefer to fill from hydrated `_source` **if already available**
  - If not hydrated yet, you may do a *cheap partial mget* for these 3 fields (or hydrate after rerank and omit these from features for now)
  - MVP acceptable: include `issued_year/volume/edition_labels` when available; otherwise omit them.

### 4) Rerank options + fallbacks
Add search-service config:
- `ranking.base-url` default `http://localhost:8082`
- `ranking.timeout-ms` default `120`
- `ranking.rerank-topk` default `50`

Behavior:
- If `ranking` is down / times out / errors:
  - proceed with existing RRF ordering (no hard failure)
  - set `strategy = "hybrid_rrf_v1"`
  - optionally include `rerank_applied=false` in debug (if you already have a debug section)

### 5) Error handling (keep existing)
- Missing/empty `query.raw` -> 400
- OpenSearch down -> 503
- Ranking down -> **not an error** (fallback)

---

## Implementation Requirements

### A) RankingGateway (thin client)
Create a thin HTTP client inside search-service:
- `services/search-service/src/main/java/.../ranking/RankingGateway.java`
- Use `RestTemplate` or `WebClient` (match the style you already used for OpenSearch)
- Apply timeout (connect+read) <= `ranking.timeout-ms`

### B) DTOs (local only)
Add local DTOs for rerank request/response inside search-service:
- `.../ranking/dto/RerankRequest.java`
- `.../ranking/dto/RerankResponse.java`

Only include fields you need:
- request: query.text, candidates[].doc_id, candidates[].features, options.size
- response: hits[].doc_id, hits[].rank, hits[].score (and debug optional)

### C) Apply ordering
Given rerank hits, reorder fused candidates:
- Use rerank order by `hits[].rank` (or list order)
- If rerank returns fewer doc_ids than requested, append remaining fused docs in original order.

---

## Testing Requirements

### Unit tests (must pass without external deps)
`cd services/search-service && ./gradlew test`
- Add tests for:
  1) when RankingGateway returns a rerank response, SearchController returns reordered hits
  2) when RankingGateway throws timeout/unavailable, SearchController still returns results (fallback)

Use mocking (Mockito) for:
- `RankingGateway`
- `OpenSearchGateway`

### Optional integration test (guarded)
If you add a smoke integration test, guard with env flag:
- `RUN_INTEGRATION=1`

---

## Validation (run and report)
1) OpenSearch up:
```bash
./scripts/local_up.sh
```

2) Start Ranking Service:
```bash
cd services/ranking-service && ./gradlew bootRun
```

3) Start Search Service:
```bash
cd services/search-service && ./gradlew bootRun
```

4) Call Search:
```bash
curl -s -XPOST "http://localhost:8080/search" \
  -H "Content-Type: application/json" \
  -d '{"query":{"raw":"해리"},"options":{"enableVector":true,"size":5}}'
```

Expect:
- `hits.length >= 1`
- `strategy` is `"hybrid_rrf_rerank_v1"` (when ranking is running)
- Stop ranking service and retry -> strategy becomes `"hybrid_rrf_v1"`

5) Unit tests:
```bash
cd services/search-service && ./gradlew test
```

---

## Output (in PR summary)
- List created/updated files
- Copy-paste commands to run locally
- Any known issues (timeouts, ranking not running, etc.)
