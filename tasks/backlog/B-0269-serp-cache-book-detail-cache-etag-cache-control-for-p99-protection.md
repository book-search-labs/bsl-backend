# B-0269 — SR Cache Layer: SERP Cache + Book Detail cache (ETag/Cache-Control) to p99 Defending

## Goal
In the Search Service/Serving section, we introduce the cache layer to stabilize**p99 delays.

- New *SERP Cache**: Same   TBD   shorten the result of the combination
- New News Book detail cache**:   TBD   To response**ETag/Cache-Control** Apply + (Optional) server cache
- For "operation" rather than the cache: TTL short, invalidation simple

## Background
- Search by tail latency for user UX (p95/p99).
- Hybrid + rerank + MIS call, the cost/conversion is spun.
- Hot Quarry/Hotdos are almost solved by cache.

## Scope
### 1) SERP Cash (required)
- Repository: Redis or in-memory Caffeine
- key:
  - `serp:{hash(q_norm + filters + sort + page + size + mode + exp_bucket + policy_version)}`
- value:
  - Total, agg summary, pipeline summary
- TTL:
  - 5~30 seconds (Basic 10 seconds) — Adjusted by traffic / freshness
- guard:
  - payload size limit (e.g. 200KB)
  - Anti-stamp cacheede(L/soft TTL optional)

### 2 years ) Book detail (ETag/Cache-Control) (required)
- Response Header:
  - `ETag`: stable hash(material_id + updated_at + schema_version)
  - New  TBD  :   TBD   (by environment)
- Tag:
  - If-None-Match Match → 304 Return
- Optional (server cache):
  - redis material id → detail payload cache (short 1~5 minutes)

### 3) Invalidation
- SERP Cash:
  - Natural Disaster with TTL Expiration (Basic)
  - prefix flush when reindex alias swap
- Details:
  - New  TBD  Change to ETag changes to natural renewal
  - Redis key delete when receiving admin update event

### 4) Observability
- hit/miss/bytes/eviction monitoring
- Comparison before/after p99 improvement

## Non-goals
- Sophisticated cache consistency (invalidation)
- CDN (Phase 9/I-0313~)

## DoD
- SERP cache operation(hit/miss log/metric)
- ETag/Cache-Control application + 304 processing on book detail response
- payload size guard, stampede minimum defense
- check p95/p99 reduction after cache adoption (with short bench)

## Interfaces
- Middleware
- Redis: serp cache + detail cache

## Metrics/Logs
- `sr_serp_cache_hit_total`, `sr_serp_cache_miss_total`
- `sr_detail_304_total`
- `sr_cache_payload_bytes_hist`
- log: request_id, cache_key_hash, hit/miss, ttl

## Codex Prompt
Implement SR caching:
- Add Redis-backed SERP cache with short TTL and payload size guard.
- Add ETag + Cache-Control handling for book detail, return 304 on If-None-Match.
- Add metrics for cache hit/miss and 304 counts.
- Ensure cache keys include query, filters, sort, paging, mode, experiment/policy version.
