# B-0608 — Chat Eval Harness (State Transition Regression)

## Priority
- P0

## Dependencies
- B-0601
- B-0603
- B-0605
- B-0611

## Goal
Q/A 정답률이 아닌 route/state/FSM 정확도를 회귀 게이트로 강제한다.

## Why
- 인터랙션 챗봇은 상태전이 오류가 실제 사고로 이어지므로 시나리오 기반 검증이 필수

## Scope
### 1) 시드 회귀셋
- 3~6턴 시나리오 20개부터 즉시 도입
- 주문 조회/환불 확인/검색 선택/모호 참조/권한 거부 포함

### 2) 검증 포인트
- turn별 `route`, `state_patch`, `pending_action transition`, `reason_code`
- 금지 claim("조회했다/실행했다") 위반 탐지

### 3) 확장
- 20 -> 100+ 시나리오 확장 계획/툴링 포함

## DoD
- CI에서 20개 시나리오가 자동 실행되고 실패 시 머지 차단
- 위반 케이스 리포트에 turn replay artifact 포함

## Interfaces
- eval runner
- regression fixtures

## Observability
- `chat_regression_pass_total{suite}`
- `chat_regression_fail_total{suite,reason}`

## Test / Validation
- fixture parser tests
- replay consistency tests

## Codex Prompt
Build a scenario-based regression harness:
- Validate route/state/FSM transitions turn by turn.
- Start with 20 critical scenarios and gate CI on failures.
- Emit replay artifacts for failed cases.
