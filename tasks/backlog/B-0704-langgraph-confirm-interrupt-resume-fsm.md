# B-0704 — LangGraph Confirm Interrupt/Resume FSM

## Priority
- P0

## Dependencies
- B-0703
- B-0392

## Goal
민감 액션(주문취소/환불/주소변경 등)을 LangGraph interrupt/resume 기반 확인 FSM으로 강제한다.

## Scope
### 1) FSM states
- `INIT -> AWAITING_CONFIRMATION -> CONFIRMED -> EXECUTING -> EXECUTED`
- 예외 상태: `EXPIRED`, `ABORTED`, `FAILED_RETRYABLE`, `FAILED_FINAL`

### 2) Interrupt/resume mechanics
- confirm 필요 시 graph interrupt 발생
- 다음 턴에서 token/의도 검증 후 resume
- pending action TTL 만료 시 자동 `EXPIRED`

### 3) Safety rails
- confirmation 없이 WRITE 실행 차단
- confirm token mismatch/재사용/만료 처리 규칙
- idempotency key 기반 중복 실행 방지

### 4) Auditability
- 상태 전이마다 action audit append
- `trace_id/request_id/reason_code/action_state` 연계

## Test / Validation
- confirm happy path tests
- wrong token / expired / abort / duplicate confirm tests
- unconfirmed write zero regression tests

## DoD
- 확인 없는 WRITE 실행이 0건이다.
- confirm 전이 로그가 100% 남는다.
- 만료/중복/오입력 케이스가 deterministic하게 처리된다.

## Codex Prompt
Implement sensitive action confirmation as LangGraph interrupt/resume FSM:
- Enforce confirmation before write execution.
- Handle token mismatch, expiry, abort, and replay safely.
- Persist transition audits for every state change.
