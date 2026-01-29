# B-0266a — Query Embedding Generating Path (OS Model vs Inference Path)

## Goal
Query Embedding generate path**

Price:
1) OpenSearch My model (using plug-in/ML function)
2) Separate Inference Path (Recommended: Absorption or Separate Embedding Service)

The BSL operating type is based on the “Service Control/Version/Version/Cost”.

## Background
- Vector retrieval is impossible without query embedding.
- When the embedding path is shaken, the delay/disability mode of SR is unstable.
- Integration with MIS allows model distribution/rollback/scan be processed in one place.

## Scope
### Decision + ADR (required)
- `ADR-00xx-embedding-path.md`
  - Select options, pros and cons, operating risks, rollback plans

### 2) API contract (option 2)
- Add endpoint to MIS:
  - POST `/v1/embeddings`
  - req: { request_id, text, model, options(max_len, normalize) }
  - res: { embedding: float[], dim, model_version, latency_ms }
- caching hint:
  - New  TBD   Return (Optional)

### 3) SR integration
- SR Vector retrieval:
  - Using cache hit → embedding
  - Cache miss → MIS Call
- fallback:
  - embedding timeout/fail → vector retrieval skip → bm25-only

### 4) Cache (optional but recommended)
- Redis:
  - key: hash(q_norm + model_version)
  - TTL: 1h~24h (Hot Quarry Week)
- guard:
  - max size, eviction policy

## Non-goals
- embedding model training
- vector index design (included separately ticket/design)

## DoD
- embedding path to ADR
- OpenAPI/JSON schema
- Call embedding in SR and degrade when timeout
- (Option) Apply Redis embedding cache
- smoke test: q_norm → embedding → chunk knn → results

## Observability
- metrics:
  - embedding_requests_total
  - embedding_cache_hit_rate
  - embedding_latency_ms
  - embedding_degrade_total
- logs:
  - request_id, q_hash, model_version, cache_hit, timeout

## Codex Prompt
Finalize query embedding path:
- Write ADR deciding OS-native vs MIS embedding endpoint (prefer MIS).
- Add /v1/embeddings endpoint contract and implement in MIS (or stub).
- Integrate SR vector retrieval to call embeddings with caching and degrade on failure.
- Add metrics for cache hit and latency, and log request_id/model_version.
