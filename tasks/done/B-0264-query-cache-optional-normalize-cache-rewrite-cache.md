# B-0264 — QS Query Cache (normalize cache + enhance cache) for cost reduction

## Goal
QS에서 반복되는 요청 비용을 줄이기 위해 캐시를 도입한다.

- **Normalize cache**: q_raw→q_norm/q_nospace/detected/canonicalKey
- **Enhance cache**: q_norm+reason→spell/rewrite/final (단, TTL/쿨다운 고려)
- 캐시는 correctness를 해치지 않도록 “짧은 TTL + versioned key”로 운영한다.

## Background
- 검색 트래픽은 헤드 쿼리가 많고(Zipf),
  normalize/enhance 결과는 재사용 가치가 높다.
- 특히 LLM/T5 결과는 비용이 크기 때문에 cache hit가 큰 절감 효과.

## Scope
### 1) Cache store
- Redis 사용
- key design은 반드시 version 포함:
  - `qs:norm:v1:{hash(q_raw|locale)}`
  - `qs:enh:v1:{hash(q_norm|reason|locale|policy_version?)}`

### 2) TTL policy (v1)
- normalize cache: 1~24h (핫쿼리 재사용 높음)
- enhance cache: 10m~2h (변화/드리프트 고려)
- negative cache(옵션): “enhance skip/deny”도 짧게 캐시(1~5m)

### 3) Cache correctness
- invalidate strategy:
  - normalize 규칙/버전 변경 시 v2로 bump
  - synonym_set이나 alias 사전 버전이 바뀌면 enhance cache key에 반영(옵션)
- payload size guard:
  - 최대 bytes 제한 + 압축(선택)

### 4) Integration points
- /query/prepare:
  - 캐시 hit → 즉시 반환
  - miss → 계산 후 set
- /query/enhance:
  - gating decision 전에 “deny cache” 확인(옵션)
  - RUN일 때만 enhance cache lookup → hit면 실행 생략

## Non-goals
- SR의 SERP cache(B-0269)
- Global governor(B-0306)

## DoD
- normalize cache가 동작하고 hit rate metric이 나온다
- enhance cache가 동작하고 LLM/T5 호출이 hit만큼 감소한다
- key에 version이 포함되어 안전하게 롤아웃 가능
- cache failure(Redis down)에서도 서비스는 정상 degrade

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
