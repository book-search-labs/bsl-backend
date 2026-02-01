# B-0229 — Redis Hot Prefix Cache for Autocomplete (TopK, TTL/size policy)

## Goal
Autocomplete p99를 방어하기 위해 **Redis hot-prefix 캐시**를 도입한다.
- prefix → TopK 후보 캐시
- cache hit: Redis만 읽고 응답
- cache miss: OpenSearch prefix query → 결과를 Redis에 저장
- TTL/size 정책으로 메모리 제어

## Background
- AC는 QPS가 높고 tail latency가 UX를 망친다.
- “OS miss path”는 필연적으로 느려서,
  hot prefix는 Redis로 끌어올려야 한다.

## Scope
### 1) Cache key/value
- key:
  - `ac:hot:{locale}:{normalized_prefix}`
- value:
  - JSON list of candidates:
    - suggest_text, score, source(popularity/ctr), (optional) payload for UI
- normalize:
  - lower/trim/NFKC(가능하면 AC에서)

### 2) Cache policy
- TTL:
  - hot prefix: 5~30 minutes (초기)
- size:
  - TopK=10~20
- negative cache:
  - 결과 없음도 짧게 캐시(예: 30~60s) to reduce OS load

### 3) Refresh / warming (optional v1.1)
- trending prefix를 미리 warm-up
- (or) AC 집계 컨슈머가 인기 prefix 업데이트 시 cache invalidate

### 4) Failure handling
- Redis down:
  - OS로 degrade (still works)
- OS down:
  - stale cache 사용(가능하면) + fallback empty

## Non-goals
- CTR/Popularity 집계(=B-0231)
- 이벤트 발행(=B-0230)

## DoD
- AC 요청 path에서 Redis hit/miss가 동작
- cache miss 시 OS 쿼리 후 Redis populate
- Redis 장애 시 degrade 동작(서비스는 200 유지 가능 범위)
- metrics로 hit rate/p99 확인 가능

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
