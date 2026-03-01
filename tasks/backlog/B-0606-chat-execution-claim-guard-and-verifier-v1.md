# B-0606 — Chat Execution Claim Guard + Verifier v1

## Priority
- P1

## Dependencies
- B-0603
- B-0604
- B-0605
- B-0611

## Goal
Tool 성공 근거 없이 "조회/실행 완료"를 말하는 허위 claim을 시스템적으로 차단한다.

## Why
- 실서비스 신뢰성 사고의 핵심 원인이 허위 완료 문구임

## Scope
### 1) Claim policy
- READ/WRITE claim 허용 조건 정의
- tool result 없는 성공 단정문 차단

### 2) Verifier pass
- compose 직전 output verifier 실행
- 위반 시 자동 repair(불확실 안내 + 대체 경로)

### 3) reason_code
- `DENY_CLAIM:NO_TOOL_RESULT`
- `DENY_CLAIM:NOT_CONFIRMED`
- `DENY_CLAIM:LOW_EVIDENCE`

## DoD
- 도구 미실행/실패 상태에서 성공 claim이 0건
- 위반 응답이 자동 교정되며 사용자 안내가 유지됨

## Interfaces
- response composer verifier hook
- tool execution receipt

## Observability
- `chat_claim_block_total{reason}`
- `chat_claim_repair_total{reason}`

## Test / Validation
- no-tool claim negative tests
- unconfirmed write claim tests
- repair template regression tests

## Codex Prompt
Add a claim verifier before response delivery:
- Block success claims unless execution evidence exists.
- Repair blocked responses into safe guidance templates.
- Track violation reason codes for ops.
