# B-0302 — Query Embedding cache/hot quarry vector cache (cost savings)

## Goal
In a hybrid search, the query embedding creation will not be bottleneck/cost:
- New *q norm → embedding vector**
- stabilizes p99 for hot queries.

## Background
- Generate query embedding in Hybrid(BM25+Vector):
  - Use external calls (LLM/model) or MIS CPU/GPU resources
  - Can greatly reduce costs/painting without changing the quality during cache

## Scope
### 1) Cache key design
- key: `emb:q:{model_version}:{locale}:{hash(q_norm)}`
- float32 vector (compressed)
- TTL:
  - Basic 1~7 days (depending on quarry distribution)
- Invalidation:
  - model version

### 2) Cache storage
- v1: Redis
- Optional: local LRU (in service instance) + Redis 2-tier

### 3) SR Integration
- When SR is hybrid request:
  1) vector retrieval
  2) Miss → embedding creation (service path matches B-0266a optional) → cache storage
- timeout budget:
  - embedding step separate timeout + bm25-only degrade

### 4) Metrics/Observability
- cache_hit_rate, cache_latency, vector_stage_latency
- Miss embedding generate failure rate
- hotkey topN(optional)

## Non-goals
- doc embedding cache (excluding checkout step)
- semantic rewrite/RAG cache(gone QS B-0264)

## DoD
- embedding cache actually works (hit/miss log/metric)
- Hybrid search P99 improved (pre/after comparison)
- model version
- bm25-only degrade

## Codex Prompt
Add query embedding caching for hybrid search:
- Implement Redis-based cache keyed by model_version+locale+q_norm hash storing float vectors.
- Integrate into SR hybrid pipeline: cache hit -> vector retrieval; miss -> generate embedding -> store -> retrieve.
- Add metrics for hit rate and latency, and ensure degrade to bm25-only on embedding timeout/failure.
