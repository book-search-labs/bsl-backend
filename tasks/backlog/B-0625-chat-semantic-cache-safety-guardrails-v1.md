# B-0625 — Chat Semantic Cache Safety Guardrails v1

## Priority
- P2

## Dependencies
- B-0624
- B-0606

## Goal
semantic cache 도입 시 오매칭/오답 재사용 위험을 제한하는 안전 가드레일을 추가한다.

## Why
- 의미 유사 기반 캐시는 비용 절감 효과가 크지만 잘못된 재사용 리스크가 큼

## Scope
### 1) Controlled adoption
- 정책/정적 정보 lane에서만 제한적 적용
- write/look-up intent는 semantic cache 금지

### 2) Confidence gating
- similarity threshold + intent/topic 동시 일치 조건
- claim verifier와 결합해 고위험 응답 재사용 차단

### 3) Drift monitoring
- cache-hit answer 품질 샘플링 + 오차율 추적

## DoD
- 고위험 인텐트에서 semantic cache 사용이 0건
- 품질 저하 시 자동 disable 토글이 동작한다.

## Interfaces
- semantic cache service
- risk policy config

## Observability
- `chat_semantic_cache_hit_total{lane}`
- `chat_semantic_cache_block_total{reason}`

## Test / Validation
- threshold boundary tests
- high-risk intent block tests
- quality drift alert tests

## Codex Prompt
Add safety constraints for semantic caching:
- Restrict usage to low-risk lanes.
- Gate cache reuse by similarity + topic/intent checks.
- Auto-disable on quality drift signals.
