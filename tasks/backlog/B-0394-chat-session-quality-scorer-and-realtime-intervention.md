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
