# T-0602 — Search Service v1.1 Hybrid MVP: lexical + vector + RRF + hydrate (Spring Boot)

## Goal
Implement the first **hybrid search execution engine** in `services/search-service` that can:
1) run **lexical (BM25)** search on `books_doc_read`
2) run **vector (kNN)** search on `books_vec_read`
3) **merge** results using **RRF (Reciprocal Rank Fusion)**
4) **hydrate** final hits by fetching display fields from `books_doc_read`
5) apply a minimal **fallback** (vector disabled on error/timeout)

This ticket is the bridge from “local indices exist” (T-0210) to “a working search API”.

---

## Must Read (SSOT)
- `AGENTS.md`
- `docs/API_SURFACE.md`
- `infra/opensearch/INDEX_VERSIONING.md` (if present)
- `infra/opensearch/books_doc_v1.mapping.json` (created in T-0210)
- `infra/opensearch/books_vec_v1.mapping.json` (created in T-0210)

If present and compatible:
- `contracts/search-request.schema.json`
- `contracts/search-response.schema.json`

> Note: If contracts are not aligned with the new qc.v1.1 yet, keep the request/response minimal but stable and document it.

---

## Scope

### Allowed
- `services/search-service/**`
- `docs/RUNBOOK.md` (add a short “Search Service local run” section)
- `scripts/test.sh` (optionally add Search Service test invocation)

### Forbidden
- `contracts/**` (do not modify)
- `infra/**` (assume T-0210 already provides local OpenSearch)
- `db/**`
- `services/query-service/**` (no coupling changes)

---

## Runtime Assumptions
- OpenSearch is running locally via T-0210:
  - `http://localhost:9200`
  - aliases exist:
    - `books_doc_read`
    - `books_vec_read`
- OpenSearch security is disabled (no auth)

---

## Target API

### POST `/search`
**Request (MVP)**
Content-Type: application/json

Option A (minimal direct query):
```json
{
  "query": { "raw": "해리포터 1권" },
  "options": {
    "size": 10,
    "from": 0,
    "enableVector": true,
    "rrfK": 60
  }
}
```

Option B (if you already use a SearchRequest schema):
- Accept the existing schema if it’s already present, but do not change contracts in this ticket.

**Response (MVP)**
```json
{
  "trace_id": "trace_xxx",
  "request_id": "req_xxx",
  "took_ms": 34,
  "strategy": "hybrid_rrf_v1",
  "hits": [
    {
      "doc_id": "b1",
      "score": 0.167,
      "rank": 1,
      "source": {
        "title_ko": "해리포터와 마법사의 돌",
        "authors": ["J.K. Rowling"],
        "publisher_name": "문학수첩",
        "issued_year": 1999,
        "volume": 1,
        "edition_labels": ["recover"]
      },
      "debug": {
        "lex_rank": 1,
        "vec_rank": 2
      }
    }
  ]
}
```

- It’s OK if `authors` in `_source` is nested; you may map it to a flat list for the response.
- Return `trace_id` and `request_id`:
  - use headers `x-trace-id`, `x-request-id` if present
  - else generate

---

## Functional Requirements

### 1) OpenSearch client config
- Configure OpenSearch endpoint in `application.yml`:
  - base URL: `http://localhost:9200`
  - indices via aliases:
    - doc index: `books_doc_read`
    - vec index: `books_vec_read`
- Provide a small `OpenSearchProperties` and config bean.

✅ Done:
- Service boots and can query OpenSearch.

---

### 2) Lexical stage (BM25)
Execute a query against `books_doc_read`.

Minimum DSL:
- `multi_match` over:
  - `title_ko`, `title_en`, `authors.name_ko`, `series_name`, `publisher_name` (use only fields that exist in mapping)
- Use query text = request `query.raw` (MVP)
- Apply base filters:
  - `must_not: { term: { is_hidden: true } }` if field exists
  - ignore if mapping doesn’t include it

Output:
- collect topK lexical hits (default 200)
- store rank position per `doc_id`

✅ Done:
- Lexical search returns >= 1 hit for “해리” on seeded data.

---

### 3) Vector stage (kNN)
Execute kNN search against `books_vec_read`.

MVP embedding:
- For this ticket, do NOT integrate an external embedding model.
- Use a deterministic “toy embedding” generator in code:
  - same input string → same 1024-d vector
  - stable across runs
  - simple approach: hash-based pseudo-random vector (normalized) using a fixed seed
- Ensure it matches the dimensionality used by T-0210 seed (`1024`).

kNN DSL:
- Use OpenSearch kNN query for `embedding`.
- topK default 200.

Failure handling:
- If kNN fails (400/500) or times out → disable vector stage and continue lexical-only.

✅ Done:
- Vector search returns >= 1 hit on seeded vec index.

---

### 4) Fusion stage (RRF)
Implement RRF merge on `doc_id`.

- Inputs:
  - lexical ranking list (doc_id → rank)
  - vector ranking list (doc_id → rank)
- Score:
  - `rrf_score = sum( 1 / (k + rank_i) )` across available lists
- Use `k` from request (default 60).
- Merge candidates up to max size (lexTopK + vecTopK).
- Sort by `rrf_score` desc.

✅ Done:
- Response includes merged hits with `score` and `rank`.
- Add debug ranks per stage in response (lex_rank, vec_rank) for now.

---

### 5) Hydration stage (doc fetch)
After fusion picks top N doc_ids:
- fetch display fields from `books_doc_read`
- preferred approach: `_mget` on `books_doc_read`
- include in response:
  - title_ko
  - authors (flatten)
  - publisher_name
  - issued_year
  - volume
  - edition_labels

✅ Done:
- Response returns readable fields even if vector stage returns only doc_id.

---

### 6) Minimal tests
Add tests to ensure the API wiring is correct.

Minimum:
- controller test for `/health`
- controller/integration-ish test for `/search`:
  - If OpenSearch is not available, allow skipping with an env flag
  - Or mock OpenSearch client for deterministic unit test

✅ Done:
- `./gradlew test` passes.

---

## Project Layout Guidance (typical)
- `api/SearchController.java`
- `service/HybridSearchService.java`
- `opensearch/OpenSearchClientConfig.java`
- `opensearch/OpenSearchGateway.java` (wraps REST calls)
- `merge/RrfFusion.java`
- `embed/ToyEmbedder.java`
- `dto/*`

---

## RUNBOOK update
Add to `docs/RUNBOOK.md`:

- Start OpenSearch: `./scripts/local_up.sh`
- Run Search Service:
  - `cd services/search-service`
  - `./gradlew bootRun`
- Test:
  - `curl -XPOST http://localhost:8080/search -H 'Content-Type: application/json' -d '{"query":{"raw":"해리"}}'`

---

## Acceptance Tests (What to run)
1) Ensure OpenSearch v1.1 is up (T-0210):
   - `./scripts/local_up.sh`
2) Start Search Service:
   - `cd services/search-service && ./gradlew bootRun`
3) Call:
   - `curl -s -XPOST http://localhost:8080/search -H 'Content-Type: application/json' -d '{"query":{"raw":"해리"},"options":{"enableVector":true}}' | jq`
4) Expect:
   - `hits.length >= 1`
   - each hit contains `doc_id`, `score`, and a hydrated `source.title_ko`
5) Run unit tests:
   - `cd services/search-service && ./gradlew test`

---

## Output (in local summary)
- List created/updated files
- Copy-paste run commands
- Any known issues (OpenSearch version / kNN query syntax differences)
