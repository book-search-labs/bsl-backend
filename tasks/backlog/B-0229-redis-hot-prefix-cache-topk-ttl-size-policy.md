# B-0229 — Redis Hot Prefix Cache for Autocomplete (TopK, TTL/size policy)

## Goal
In order to defend the Autocomplete p99, we will introduce the Redis hot-prefix cache**.
- prefix → TopK candidate cache
- cache hit: Redis only read and respond
- cache miss: OpenSearch prefix query → Save result in Redis
- Memory control with TTL/size policy

## Background
- AC is a high QPS and the tail latency spoils UX.
- "OS miss path",
hot prefix should be pulled to Redis.

## Scope
### 1) Cache key/value
- key:
  - `ac:hot:{locale}:{normalized_prefix}`
- value:
  - JSON list of candidates:
    - suggest_text, score, source(popularity/ctr), (optional) payload for UI
- normalize:
  - lower/trim/NFKC(AC if possible)

### 2) Cache policy
- TTL:
  - hot prefix: 5~30 minutes
- size:
  - TopK=10~20
- negative cache:
  - Short Cash(e.g. 30~60s) to reduce OS load

### 3) Refresh / warming (optional v1.1)
- Warm-up trending prefix
- (or) AC aggregate contactor popular prefix update cache invalidate

### 4) Failure handling
- Redis down:
  - degrade (still works)
- OS down:
  - use stale cache + fallback empty

## Non-goals
- CTR/Popularity Aggregation(=B-0231)
- Issued Event(=B-0230)

## DoD
- Redis hit/miss action in the request path
- Redis populate after cache miss
- Degrade operation when Redis failure (services are maintained 200)
- metrics to hit rate/p99

## Observability
- metrics:
  - ac_cache_hit_total, ac_cache_miss_total
  - ac_cache_hit_rate
  - ac_os_fallback_total
  - ac_latency_ms(p50/p95/p99)
- logs:
  - prefix hash, hit/miss, os_query_time

## Codex Prompt
Implement Redis-based hot prefix cache for autocomplete:
- cache key scheme with normalization
- store TopK candidates JSON with TTL and negative caching
- on miss query OpenSearch then populate Redis
- add metrics for hit/miss and latency, and degrade behavior when Redis/OS fails
