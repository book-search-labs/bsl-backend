# B-0394 — Chat Session Quality Scorer + Realtime Intervention

## Priority
- P1

## Dependencies
- B-0357, B-0375, B-0391
- B-0392, B-0393

## Goal
세션 단위 품질 점수를 실시간 계산하고, 품질 저하를 조기 감지해 사용자 이탈 전에 개입(intervention)한다.

## Scope
### 1) Session quality scorer
- turn별 신호(근거율, 재질문율, 오류율, completion 여부)로 세션 점수 계산
- 세션 상태를 `HEALTHY`, `AT_RISK`, `DEGRADED`로 분류
- intent별 가중치 프로파일 분리(커머스/일반질문)

### 2) Realtime intervention policy
- `AT_RISK` 도달 시: 요약 재확인 + 빠른 액션 버튼 제시
- `DEGRADED` 도달 시: 안전모드 전환 + 티켓/상담 전환 우선 제시
- 동일 세션 연속 실패 시 자동 escalation

### 3) Closed-loop learning
- intervention 이후 회복률/완료율을 모델링 피드백으로 적재
- 무효 intervention 패턴은 자동 감쇠

## Observability
- `chat_session_quality_score_hist{intent}`
- `chat_session_state_total{state}`
- `chat_intervention_total{type,result}`
- `chat_intervention_recovery_rate{type}`

## Test / Validation
- synthetic session replay로 상태 전이 검증
- intervention 이후 completion uplift A/B 테스트
- false alarm rate(불필요 개입률) 상한 검증

## DoD
- 세션 위험 상태를 실시간 탐지하고 사용자 개입이 동작
- 개입 후 회복률 지표가 대시보드에서 추적 가능
- 고위험 세션의 티켓 전환 누락률이 유의미하게 감소

## Codex Prompt
Add a real-time session quality scorer:
- Score chat sessions per turn and classify health states.
- Trigger policy-based interventions for at-risk/degraded sessions.
- Measure recovery/completion lift and close the feedback loop.

## Implementation Update (2026-03-04, Bundle 1)
- [x] Session quality scorer guard gate 추가
  - `scripts/eval/chat_session_quality_scorer_guard.py`
  - intent 프로파일(commerce/general) 점수 산식 계산 및 평균 품질 점수 검증
  - reported score 대비 model drift 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_session_quality_scorer_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_SESSION_QUALITY_SCORER_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 2)
- [x] Session state transition guard gate 추가
  - `scripts/eval/chat_session_state_transition_guard.py`
  - 상태 분류(HEALTHY/AT_RISK/DEGRADED) 집계 및 state mismatch 검증
  - invalid transition(특히 DEGRADED→HEALTHY 직행) 및 false alarm 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_session_state_transition_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_SESSION_STATE_TRANSITION_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 3)
- [x] Realtime intervention policy guard gate 추가
  - `scripts/eval/chat_realtime_intervention_policy_guard.py`
  - `AT_RISK/DEGRADED` 상태별 필수 intervention type 누락 검증
  - 연속 실패 임계치 초과 시 escalation 누락 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_realtime_intervention_policy_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_REALTIME_INTERVENTION_POLICY_GUARD=1 ./scripts/test.sh`
