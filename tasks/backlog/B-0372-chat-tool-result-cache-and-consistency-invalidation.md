# B-0372 — Chat Tool Result Cache + Consistency Invalidation

## Priority
- P2

## Dependencies
- B-0359, B-0364, B-0367

## Goal
반복 조회 인텐트(주문상태/배송조회)에서 응답 지연을 줄이되, 잘못된 캐시로 오답이 발생하지 않도록 정합성 무효화 정책을 도입한다.

## Scope
### 1) Cache strategy
- tool별 cache key 규칙(user_id + tool + params hash)
- TTL 클래스(짧음/중간/길음) 정의

### 2) Invalidation triggers
- 주문/배송 상태 이벤트 수신 시 연관 캐시 무효화
- 민감 필드 조회는 cache bypass 옵션 지원

### 3) Staleness guard
- stale 가능 응답에 freshness stamp 표시
- stale threshold 초과 시 강제 원본 조회

### 4) Safety fallback
- cache corruption 감지 시 cache disable + 원본 fallback

## Observability
- `chat_tool_cache_hit_total{tool}`
- `chat_tool_cache_stale_block_total{tool}`
- `chat_tool_cache_invalidate_total{reason}`
- `chat_tool_cache_bypass_total{tool}`

## Test / Validation
- hit/miss/expire/invalidate 시나리오 테스트
- 이벤트 기반 무효화 회귀 테스트
- stale 응답 차단 테스트

## DoD
- 주요 tool 조회 p95 latency 개선
- stale 캐시 오답 비율 감소
- 캐시 무효화 실패를 모니터링으로 탐지 가능

## Codex Prompt
Add safe caching for chat tool results:
- Cache read-heavy tool responses with per-tool TTL policies.
- Invalidate via order/shipping domain events and staleness guards.
- Ensure stale/corrupt cache never bypasses correctness checks.

## Implementation Update (2026-03-03, Bundle 1)
- [x] Tool cache strategy gate 추가
  - `scripts/eval/chat_tool_cache_strategy.py`
  - lookup 대비 hit/miss/bypass 비율, cache key 필수 필드(user/tool/params hash) 누락 검증
  - ttl class(`SHORT/MEDIUM/LONG`) 미정의 및 정책 범위 벗어난 TTL을 게이트화
  - gate 모드에서 hit ratio 저하, bypass 과다, key/TTL 정책 위반, stale evidence 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_tool_cache_strategy.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_TOOL_CACHE_STRATEGY=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Tool cache invalidation gate 추가
  - `scripts/eval/chat_tool_cache_invalidation.py`
  - 도메인 이벤트(order/shipping) 대비 invalidate 커버리지/지연(lag) 검증
  - resource key 누락, invalidation reason 누락, missing/late invalidate 건수 게이트화
  - gate 모드에서 커버리지 저하, 무효화 누락/지연, stale evidence 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_tool_cache_invalidation.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_TOOL_CACHE_INVALIDATION=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 3)
- [x] Tool cache staleness guard gate 추가
  - `scripts/eval/chat_tool_cache_staleness_guard.py`
  - stale threshold 초과 응답의 block/fallback/leak 여부와 freshness stamp 누락을 검증
  - stale leak, block ratio 저하, freshness stamp 누락을 게이트화
  - gate 모드에서 stale guard 위반 및 stale evidence 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_tool_cache_staleness_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_TOOL_CACHE_STALENESS_GUARD=1 ./scripts/test.sh`
