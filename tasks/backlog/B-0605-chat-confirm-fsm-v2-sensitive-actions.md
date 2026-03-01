# B-0605 — Chat Confirm FSM v2 for Sensitive Actions

## Priority
- P0

## Dependencies
- B-0601
- B-0604
- B-0611
- B-0613

## Goal
민감 액션 실행 전후 상태전이를 FSM으로 강제해 무확인 실행/중복 실행 사고를 차단한다.

## Why
- confirmation 흐름이 느슨하면 환불/취소 오실행 사고가 발생함

## Scope
### 1) FSM states
- `INIT` -> `AWAITING_CONFIRMATION` -> `CONFIRMED` -> `EXECUTING` -> `EXECUTED`
- abort/fail: `ABORTED`, `EXPIRED`, `FAILED_RETRYABLE`, `FAILED_FINAL`

### 2) Transition guard
- confirmation TTL(예: 5분)
- max retry budget
- authz 재검증 후 execute 진입

### 3) Audit trail
- 모든 전이 이벤트를 action audit에 append

## DoD
- confirmation 없이 write execute가 0건이다.
- 만료/중복 confirm 처리 규칙이 일관되게 동작한다.
- 전이 로그로 사고 재현이 가능하다.

## Interfaces
- pending_action state
- action executor

## Observability
- `chat_confirm_fsm_transition_total{from,to}`
- `chat_confirm_expired_total{action_type}`
- `chat_execute_block_total{reason=not_confirmed}`

## Test / Validation
- confirm happy path tests
- expired/aborted/retry paths
- duplicate confirm race tests

## Codex Prompt
Implement confirm-state machine for sensitive actions:
- Enforce explicit state transitions with TTL/retry limits.
- Block execution without valid confirmation.
- Record every transition in audit logs.
