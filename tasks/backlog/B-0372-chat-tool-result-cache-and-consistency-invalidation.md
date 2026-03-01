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
