# B-0392 — Chat Action Ledger + Idempotent Workflow State Machine

## Priority
- P0

## Dependencies
- B-0359, B-0367, B-0370, B-0382
- B-0391

## Goal
책봇이 주문/배송/환불 액션을 수행할 때 중복 실행·상태 불일치·부분 실패를 방지하도록 액션 원장(Action Ledger)과 멱등 워크플로우 상태머신을 도입한다.

## Scope
### 1) Action ledger
- `chat_action_ledger` 테이블 추가: action_id, session_id, user_id, intent, workflow_step, idempotency_key, status, reason_code, payload_hash, created_at
- 동일 idempotency_key 재요청은 재실행 대신 기존 결과 반환
- step 단위 성공/실패/보상(compensation) 기록

### 2) Workflow state machine
- 주문조회/배송조회/환불문의 워크플로우 상태 정의
- 허용 전이만 통과 (invalid transition 차단)
- partial failure 시 단계별 retry/backoff + 최종 safe-abort

### 3) Ticket integration safety
- 액션 실패/불일치 시 자동 티켓 생성 트리거
- 티켓 생성 전후 상태를 ledger와 양방향 연결
- "사용자에게 완료 안내했지만 실제 액션 실패" 케이스를 강제 검출

### 4) Observability
- action success/fail/compensation 지표
- 중복 요청 억제율, invalid transition 비율
- 워크플로우 단계별 p95 latency

## Data / Schema
- `chat_action_ledger` (new)
- `chat_action_transition_log` (new, optional)
- contracts 변경 필요 시 별도 PR 분리

## Test / Validation
- 같은 action 재요청 100회 멱등성 테스트
- 강제 실패(툴 timeout/5xx) 시 보상 시나리오 회귀 테스트
- 상태 불일치 탐지 테스트(주문취소 vs 배송완료 등)

## DoD
- 중복 액션이 재실행되지 않고 안정적으로 재사용됨
- 상태 전이 위반 케이스가 모두 차단됨
- 실패 케이스가 티켓/로그/메트릭에 일관되게 반영됨

## Codex Prompt
Implement a production-safe action ledger for chat:
- Add idempotent workflow state machine per commerce intent.
- Persist step transitions and compensation outcomes.
- Auto-detect inconsistent states and trigger ticket escalation.
