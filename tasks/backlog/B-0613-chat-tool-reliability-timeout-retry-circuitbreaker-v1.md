# B-0613 — Chat Tool Reliability v1 (Timeout/Retry/Circuit Breaker)

## Priority
- P0

## Dependencies
- B-0604
- B-0605
- B-0611

## Goal
Tool 실패 상황에서도 중복 실행/무한 재시도/사용자 방치를 막는 표준 복구 경로를 제공한다.

## Why
- 도구 실패 시 정책 부재는 오실행과 사용자 불신을 동시에 유발함

## Scope
### 1) Reliability contract
- 표준 timeout/retry budget
- circuit breaker(open/half-open/closed)

### 2) Idempotent write
- write tool 호출 전역 idempotency key 적용
- 이미 처리된 요청 재호출 시 safe replay

### 3) Failure UX policy
- 실패 후 next action을 `RETRY` / `OPEN_SUPPORT_TICKET` / `STATUS_CHECK` 중 하나로 고정

## DoD
- timeout/retry 정책이 tool별 일관 적용된다.
- write 중복 실행이 0건으로 유지된다.
- 실패 응답이 표준 next_action으로 반환된다.

## Interfaces
- tool client wrapper
- circuit breaker module

## Observability
- `chat_tool_call_total{tool,result}`
- `chat_tool_timeout_total{tool}`
- `chat_circuit_breaker_state{tool,state}`

## Test / Validation
- timeout + retry exhaustion tests
- breaker transition tests
- duplicate write replay tests

## Codex Prompt
Standardize tool reliability behavior:
- Add timeout/retry budgets and circuit breaker wrapper.
- Guarantee idempotent write-tool execution.
- Return fixed failure UX actions on tool errors.
