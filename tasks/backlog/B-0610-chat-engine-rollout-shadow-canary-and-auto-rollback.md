# B-0610 — Chat Engine Rollout (Shadow/Canary/Auto Rollback)

## Priority
- P1

## Dependencies
- B-0608
- B-0609
- B-0391
- I-0352

## Goal
legacy 챗 엔진에서 agent 엔진으로 안전하게 전환하기 위한 점진 배포 체계를 구축한다.

## Why
- 인터랙션 엔진 전환은 품질 회귀/오실행 리스크가 크므로 즉시 롤백 경로가 필수

## Scope
### 1) Engine flag
- `chat.engine=legacy|agent`
- 세션/사용자/트래픽 비율 단위 제어

### 2) Rollout stages
- 0% shadow compare
- 5% canary
- 점진 확대 + SLO 위반 시 auto rollback

### 3) Gate conditions
- 무확인 write 0건
- authz 사고 0건
- state transition pass rate >= 99%

## DoD
- shadow/canary 결과가 자동 집계된다.
- 기준 위반 시 1분 이내 rollback 가능하다.
- rollout 이력/결정 사유가 감사 추적된다.

## Interfaces
- feature flag config
- rollout controller

## Observability
- `chat_rollout_traffic_ratio{engine}`
- `chat_rollout_rollback_total{reason}`

## Test / Validation
- shadow diff tests
- canary gate simulation tests
- rollback smoke tests

## Codex Prompt
Implement safe engine rollout controls:
- Add feature-flag based engine routing.
- Support shadow and canary phases with hard quality gates.
- Trigger automatic rollback on gate violations.
