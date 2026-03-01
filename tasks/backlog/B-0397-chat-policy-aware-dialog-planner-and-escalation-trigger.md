# B-0397 — Chat Policy-aware Dialog Planner + Escalation Trigger

## Priority
- P0

## Dependencies
- B-0395, B-0396
- B-0371, A-0154

## Goal
책봇이 대화를 "정책/상태/사용자 목표"에 맞춰 단계적으로 계획하고, 해결 불가능 케이스는 지연 없이 적절한 에스컬레이션으로 전환한다.

## Scope
### 1) Dialog planner core
- 의도별 상태 머신(확인 -> 판단 -> 실행 -> 검증) 정의
- 정책 제약(반품기한/환불수수료/권한검증)을 단계 전이 조건으로 강제
- 단계별 필수 슬롯 미충족 시 질문 전략 자동 선택

### 2) Escalation trigger engine
- 반복 실패/고위험 reason_code/사용자 불만 신호 기반 자동 에스컬레이션
- 에스컬레이션 임계치와 쿨다운 정책(versioned) 관리
- 불필요한 조기 이관(과민 반응) 방지를 위한 confidence hysteresis 적용

### 3) Case handover payload
- 에스컬레이션 시 대화 요약, 실행된 액션, 정책 판단 근거를 패키징
- 운영자가 재질문 없이 즉시 처리 가능한 최소 데이터셋 강제
- 민감 필드는 마스킹 규칙 적용

### 4) Planner evaluation gate
- 플래너 경로 이탈률/단계 누락률/잘못된 에스컬레이션률 측정
- 기준치 초과 시 릴리스 차단 또는 부분 롤백 신호 발행

## Observability
- `chat_dialog_planner_transition_total{intent,from,to,result}`
- `chat_escalation_trigger_total{reason_code,level}`
- `chat_escalation_false_positive_rate`
- `chat_planner_path_deviation_total{intent}`

## Test / Validation
- 의도별 상태 전이 회귀 테스트
- 조기 이관/이관 누락 시나리오 테스트
- 상담 이관 payload 완전성 검증

## DoD
- 챗봇 단계 진행이 정책/상태와 일관되게 동작함
- 해결 불가 케이스의 이관 누락률이 목표치 이하로 감소
- 상담 이관 후 재질문 빈도가 유의미하게 감소

## Codex Prompt
Implement a policy-aware dialog planner for production chat:
- Drive conversations through explicit state transitions with policy guards.
- Trigger escalation on repeated failure and risk patterns.
- Package complete handover payloads and gate releases on planner reliability.
