# B-0264 — QS Query Cache (normalize cache + enhance cache) for cost reduction

## Goal
QS introduces cache to reduce repeated request costs.

- **Normalize cache**: q_raw→q_norm/q_nospace/detected/canonicalKey
- New *Enhance cache**: q norm+reason→spell/rewrite/final(Single, TTL/cooldown consideration)
- The cache will be operated as "short TTL + versioned key" to avoid correctness.

## Background
- Search traffic has many head queries (Zipf),
Normalize/enhance results increase reuse value.
- Especially the LLM/T5 result is a large savings effect of cache hit due to expensive size.

## Scope
### 1) Cache store
- Redis
- key design includes:
  - `qs:norm:v1:{hash(q_raw|locale)}`
  - `qs:enh:v1:{hash(q_norm|reason|locale|policy_version?)}`

### 2) TTL policy (v1)
- Normalize cache: 1~24h (Hot quarry reuse high)
- Enhance cache: 10m~2h (change/drop consideration)
- negative cache (optional): “enhance skip/deny” short cache(1~5m)

### 3) Cache correctness
- invalidate strategy:
  - normalize Bump to v2 when the rule/version changes
  - If synonym set or alias pre-version changes, reflect enhance cache key(optional)
- payload size guard:
  - Maximum bytes limit + compression(optional)

### 4) Integration points
- /query/prepare:
  - cache hit → instant return
  - set after calculation
- /query/enhance:
  - Check “deny cache” before gating decision (optional)
  - RUN when only enhance cache lookup → hit when running

## Non-goals
- SR SERP cache(B-0269)
- Global governor(B-0306)

## DoD
- Normalize cache is running and hit rate metric
- Enhance cache runs and LLM/T5 calls are reduced as hit
- You can roll out the version in key safely
- service top degrade even in cache failure(Redis down)

## Observability
- metrics:
  - qs_norm_cache_hit_total / miss_total
  - qs_enh_cache_hit_total / miss_total
  - qs_cache_errors_total
- logs:
  - request_id, cache_hit flags, key_version

## Codex Prompt
Add QS caching:
- Implement Redis-based normalize and enhance caches with versioned keys.
- Define TTL policies and payload guards.
- Ensure cache is best-effort (Redis failure does not fail requests).
- Emit cache hit/miss/error metrics and log flags.
