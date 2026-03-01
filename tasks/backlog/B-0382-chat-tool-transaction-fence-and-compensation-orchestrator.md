# B-0382 — Chat Tool Transaction Fence + Compensation Orchestrator

## Priority
- P1

## Dependencies
- B-0359, B-0367, B-0369

## Goal
다단계 tool 실행 중 일부만 반영되는 문제를 막기 위해 트랜잭션 경계(fence)와 보상(compensation) 오케스트레이션을 도입한다.

## Scope
### 1) Transaction fence model
- workflow 단위 `prepare -> validate -> commit` 단계 분리
- commit 전 최종 상태 재검증(optimistic check)

### 2) Idempotency and dedup
- tool call별 idempotency key 강제
- 재시도 중 중복 side-effect 차단

### 3) Compensation actions
- 실패 시 이전 단계 롤백/보상 액션 정의
- 보상 실패 시 안전정지 + 운영 알림

### 4) Auditability
- 단계별 상태전이 로그 및 reason_code 저장
- 사후 재생(replay) 가능한 실행 기록 제공

## Observability
- `chat_tool_tx_started_total{workflow}`
- `chat_tool_tx_commit_total{workflow,result}`
- `chat_tool_tx_compensation_total{workflow,result}`
- `chat_tool_tx_inconsistent_state_total`

## Test / Validation
- 부분실패/재시도/중복호출 시나리오 테스트
- 보상 액션 성공/실패 회귀 테스트
- 최종 상태 일관성 검증 테스트

## DoD
- 부분반영/중복반영 이슈 감소
- 실패 시 안전 보상 동작 보장
- 트랜잭션 실행 이력 추적 가능

## Codex Prompt
Add transactional safety for multi-tool chat actions:
- Introduce prepare/commit fences with optimistic checks.
- Enforce idempotency keys and dedup on retries.
- Execute compensation on partial failures with full audit trails.
