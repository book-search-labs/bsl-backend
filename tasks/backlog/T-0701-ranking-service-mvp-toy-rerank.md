# T-0701 — Ranking Service MVP: `/health`, `/rerank` (Toy Reranker)

## Goal
Implement a **minimal Ranking Service** that can take **Top-K candidates** from Search Service and return a **re-ordered list** with scores.

This is the bridge from:
- **T-0602 Search Service hybrid retrieval (BM25 + kNN + RRF + hydrate)**  
to:
- a **pluggable reranking stage** (later: LightGBM LambdaMART / Cross-Encoder / LLM rerank)

MVP focuses on **API shape + deterministic behavior + testability**, not model quality.

---

## Must Read (SSOT)
- `AGENTS.md`
- `docs/API_SURFACE.md`
- `docs/ARCHITECTURE.md` (or `docs/INDEXING.md` if that’s where the pipeline is described)
- `tasks/backlog/T-0602-search-service-hybrid-rrf-mvp.md` (to align the handoff)

If present:
- `contracts/rerank-request.schema.json`
- `contracts/rerank-response.schema.json`

> Note: This ticket must **not** edit `contracts/**`. If contracts are missing/outdated, keep DTOs local to `services/ranking-service` and document the MVP request/response format in the service README.

---

## Scope

### Allowed
- `services/ranking-service/**`
- `docs/RUNBOOK.md` (add a short “Ranking Service local run” section)
- `scripts/test.sh` (optionally add Ranking Service test invocation)

### Forbidden
- `infra/**`
- `contracts/**`
- `db/**`
- `services/search-service/**`
- `services/query-service/**`

---

## Runtime Assumptions
- This service is **standalone**. No DB.
- It should run locally without OpenSearch.
- Default port:
  - Spring Boot: `8082` (recommended to avoid conflicts)

---

## Target API

### 1) GET `/health`
**Response**
- HTTP 200
- Body:
```json
{ "status": "ok" }
```

---

### 2) POST `/rerank`
**Request (MVP)**
Content-Type: application/json

```json
{
  "query": {
    "text": "해리포터 1권"
  },
  "candidates": [
    {
      "doc_id": "b1",
      "features": {
        "lex_rank": 1,
        "vec_rank": 2,
        "rrf_score": 0.167,
        "issued_year": 1999,
        "volume": 1,
        "edition_labels": ["recover"]
      }
    }
  ],
  "options": {
    "size": 10
  }
}
```

**Notes**
- `query.text` is the string the reranker should consider (Search Service will send `query.final` or `query.raw` depending on future QueryContext evolution).
- `candidates[*].features` is optional. If missing, reranker must still return a deterministic ordering (fallback to input order / doc_id).

**Response (MVP)**
```json
{
  "trace_id": "trace_xxx",
  "request_id": "req_xxx",
  "took_ms": 7,
  "model": "toy_rerank_v1",
  "hits": [
    {
      "doc_id": "b1",
      "score": 1.234,
      "rank": 1,
      "debug": {
        "base_rrf": 0.167,
        "lex_bonus": 0.50,
        "vec_bonus": 0.20,
        "freshness_bonus": 0.10,
        "slot_bonus": 0.15
      }
    }
  ]
}
```

**ID handling**
- Extract `trace_id`, `request_id` from headers `x-trace-id`, `x-request-id` if present
- Else generate UUIDs

**Error handling**
- Missing or empty `query.text` → HTTP 400 `{ error: { code, message }, trace_id, request_id }`
- Missing `candidates` or empty list → HTTP 400 (same error shape)
- Non-JSON body → HTTP 400
- Any unexpected exception → HTTP 500 (same error shape)

---

## Reranking Logic (Toy Model, Deterministic)
Implement a simple scoring function that is:
- deterministic (same input → same output)
- stable across runs
- explainable via debug fields

### Inputs
For each candidate:
- `lex_rank` (int, lower is better)
- `vec_rank` (int, lower is better)
- `rrf_score` (float, higher is better)
- optional catalog-ish hints:
  - `issued_year` (int)
  - `volume` (int)
  - `edition_labels` (array of strings)

### Toy score (recommended)
Let:
- `base = rrf_score` (default 0 if missing)
- `lex_bonus = 1.0 / (60 + lex_rank)` if present else 0
- `vec_bonus = 1.0 / (60 + vec_rank)` if present else 0
- `freshness_bonus = clamp((issued_year - 1980) / 100, 0, 0.5)` if present else 0
- `slot_bonus`:
  - if `volume` exists and > 0 → +0.10
  - if edition_labels contains `"recover"` → +0.05

Final:
- `score = base + 2.0*lex_bonus + 1.0*vec_bonus + 0.2*freshness_bonus + slot_bonus`

Tie-breaker:
1) higher `score`
2) lower `lex_rank` (if present)
3) lower `vec_rank` (if present)
4) lexicographical `doc_id`

✅ Done:
- Scores computed and sorted deterministically.
- Response includes `debug` components.

---

## Project Layout (Spring Boot)
`services/ranking-service/`

- `build.gradle`
- `src/main/java/...`
  - `api/RankingController.java`
  - `api/dto/*` (request/response/error DTOs)
  - `service/ToyRerankService.java`
  - `service/Scoring.java` (pure function)
  - `RankingServiceApplication.java`
- `src/test/java/...`
  - `RankingControllerTest.java`
  - `ToyRerankServiceTest.java`
- `application.yml`
  - `server.port: 8082`

Follow existing repo conventions if a skeleton already exists.

---

## Tests (Minimum)
Must pass:
- `cd services/ranking-service && ./gradlew test`

Required tests:
1) `/health` returns 200 + `{status:"ok"}`
2) `/rerank` happy-path (3 candidates):
   - asserts response 200
   - output hits length = min(options.size, candidates.size)
   - ordering is deterministic (expected top doc_id)
3) `/rerank` invalid input:
   - empty query.text OR empty candidates
   - returns 400 with error body

✅ Done:
- `./gradlew test` passes on a clean checkout.

---

## README / RUNBOOK
Create or update:
- `services/ranking-service/README.md`
  - how to run
  - how to test
  - curl example
- Update `docs/RUNBOOK.md` with a short section:

```bash
# Ranking Service
cd services/ranking-service
./gradlew bootRun
curl -s -XPOST http://localhost:8082/rerank -H 'Content-Type: application/json' \
  -d '{"query":{"text":"해리"},"candidates":[{"doc_id":"b1","features":{"rrf_score":0.1,"lex_rank":1}},{"doc_id":"b2","features":{"rrf_score":0.1,"lex_rank":2}}],"options":{"size":5}}'
```

---

## Acceptance Tests (What to run)
1) Start service:
```bash
cd services/ranking-service
./gradlew bootRun
```

2) Health:
```bash
curl -s http://localhost:8082/health
```

3) Rerank:
```bash
curl -s -XPOST http://localhost:8082/rerank \
  -H 'Content-Type: application/json' \
  -H 'x-trace-id: trace_demo' \
  -H 'x-request-id: req_demo' \
  -d '{
    "query": {"text": "해리포터 1권"},
    "candidates": [
      {"doc_id":"b1","features":{"rrf_score":0.167,"lex_rank":1,"vec_rank":2,"issued_year":1999,"volume":1,"edition_labels":["recover"]}},
      {"doc_id":"b2","features":{"rrf_score":0.150,"lex_rank":2,"vec_rank":1,"issued_year":2000,"volume":2,"edition_labels":[]}}
    ],
    "options":{"size":10}
  }'
```

4) Run tests:
```bash
cd services/ranking-service
./gradlew test
```

---

## Output (in local summary)
- List created/updated files
- Copy-paste run commands
- Any known issues (ports)
