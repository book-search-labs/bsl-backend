# B-0367 — Chat Workflow Engine (멀티스텝 커머스 지원)

## Priority
- P1

## Dependencies
- B-0359, B-0363, B-0364

## Goal
주문취소/환불접수/배송지 변경처럼 여러 단계를 거치는 요청을 챗봇에서 상태 기반으로 안전하게 처리한다.

## Non-goals
- 커머스 도메인 상태머신 자체를 전면 개편하지 않는다.
- 상담사 시스템을 대체하지 않는다.

## Scope
### 1) Workflow state model
- workflow_id, current_step, required_inputs, last_action_at 정의
- 주문취소/환불접수/배송지변경 템플릿 워크플로우 우선 지원

### 2) Plan-and-execute
- 사용자 의도 확인 -> 필요 정보 수집 -> 검증 -> 실행 호출 순서 고정
- step 실패 시 이전 단계 재진입 또는 대체 경로 제시

### 3) Confirmation checkpoints
- 금전/환불/주문상태 변경은 실행 직전 최종 확인 필수
- 확인 응답 timeout 시 자동 취소

### 4) Recovery + audit
- 세션 중단 후 workflow 복원
- 단계별 tool 호출/결정 근거 audit trail 저장

## Observability
- `chat_workflow_started_total{type}`
- `chat_workflow_completed_total{type,result}`
- `chat_workflow_step_error_total{type,step,error_code}`
- `chat_workflow_recovery_total{result}`

## Test / Validation
- 멀티스텝 정상 완료 시나리오(e2e) 3종
- step 누락/입력 오류/권한 오류/timeout 회귀 테스트
- 중간 이탈 후 재진입 복원 테스트

## DoD
- 멀티스텝 요청의 완료율 개선
- 민감 액션 무확인 실행 0건
- 실패 워크플로우에서 사용자 재시도 성공률 개선

## Codex Prompt
Implement a stateful chat workflow engine for commerce support:
- Add workflow state, step orchestration, and mandatory confirmation checkpoints.
- Support interruption recovery and deterministic re-entry.
- Persist per-step audit records and reliability metrics.
