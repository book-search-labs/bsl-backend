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

## Implementation Update (2026-03-04, Bundle 1)
- [x] Dialog planner core guard gate 추가
  - `scripts/eval/chat_dialog_planner_core_guard.py`
  - 상태전이 유효성(확인→판단→실행→검증) 및 path deviation 검증
  - 정책 차단 상태에서 전이 성공(policy block violation) 검증
  - 필수 슬롯 미충족 시 질문 전략 누락 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_dialog_planner_core_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_DIALOG_PLANNER_CORE_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 2)
- [x] Escalation trigger engine guard gate 추가
  - `scripts/eval/chat_escalation_trigger_engine_guard.py`
  - 반복 실패/고위험 reason/사용자 불만 신호 기반 trigger recall 검증
  - cooldown/hysteresis 억제 경로와 false positive 비율 검증
  - threshold version 누락 및 trigger missed 건수 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_escalation_trigger_engine_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_ESCALATION_TRIGGER_ENGINE_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 3)
- [x] Case handover payload guard gate 추가
  - `scripts/eval/chat_case_handover_payload_guard.py`
  - 에스컬레이션 payload 최소 필드(요약/실행액션/정책근거) 완전성 검증
  - payload 누락/불완전으로 인한 재질문 리스크 지표 검증
  - 민감 필드 마스킹 위반 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_case_handover_payload_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_CASE_HANDOVER_PAYLOAD_GUARD=1 ./scripts/test.sh`
