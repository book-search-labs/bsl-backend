# B-0377 — Chat Source Conflict Resolution + Safe Abstention

## Priority
- P1

## Dependencies
- B-0360, B-0365, B-0368

## Goal
이벤트/공지/정책 출처 간 상충 정보가 있을 때, 챗봇이 잘못된 단정 답변을 하지 않도록 충돌 감지와 안전 보류(abstention) 흐름을 도입한다.

## Scope
### 1) Conflict detection
- 동일 주제의 다중 출처 간 날짜/금액/정책 조건 충돌 탐지
- 충돌 강도(`LOW/MEDIUM/HIGH`) 산출

### 2) Resolution policy
- 최신 공식 출처 우선 규칙
- 고충돌 시 단정 답변 금지 + 확인 경로 안내

### 3) User messaging
- "정보가 상충되어 확인이 필요함" 한국어 표준 문구
- 사용자에게 확인 가능한 출처 링크 제시

### 4) Operator feedback
- 상충 케이스를 운영 큐(A-0144)로 자동 전달
- 출처 품질 개선 루프와 연결

## Observability
- `chat_source_conflict_detected_total{severity}`
- `chat_source_conflict_abstain_total`
- `chat_source_conflict_resolved_total{strategy}`
- `chat_conflict_operator_queue_total`

## Test / Validation
- 인위적 상충 데이터셋 기반 검증
- 충돌 강도별 답변 정책 회귀 테스트
- 잘못된 단정 응답 차단 테스트

## DoD
- 상충 데이터 상황에서 오답 단정 비율 감소
- abstain/fallback 응답 일관성 확보
- 운영자가 상충 원인을 추적/수정 가능

## Codex Prompt
Implement conflict-aware chat grounding:
- Detect contradictory facts across sources and score conflict severity.
- Apply safe abstention and official-source preference policies.
- Route conflict cases to operators and track resolution outcomes.

## Implementation Update (2026-03-03, Bundle 1)
- [x] Conflict detection gate 추가
  - `scripts/eval/chat_source_conflict_detection.py`
  - 충돌 강도(severity) 유효성 및 토픽/유형/source pair/evidence 완전성 검증
  - gate 모드에서 감지 품질 임계치 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_source_conflict_detection.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_SOURCE_CONFLICT_DETECTION=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Conflict resolution policy gate 추가
  - `scripts/eval/chat_source_conflict_resolution_policy.py`
  - HIGH 충돌에서 unsafe 결정(단정/실행) 차단 여부 검증
  - official source available 시 공식출처 우선 적용률 검증
  - resolution rate/strategy 유효성/policy_version/reason_code 누락 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_source_conflict_resolution_policy.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_SOURCE_CONFLICT_RESOLUTION_POLICY=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 3)
- [x] Safe abstention messaging gate 추가
  - `scripts/eval/chat_source_conflict_safe_abstention.py`
  - should-abstain 케이스의 unsafe definitive 응답 차단 검증
  - 한국어 표준문구/출처링크 포함 여부 검증
  - reason_code 누락 및 메시지 품질 비율 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_source_conflict_safe_abstention.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_SOURCE_CONFLICT_SAFE_ABSTENTION=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 4)
- [x] Operator feedback gate 추가
  - `scripts/eval/chat_source_conflict_operator_feedback.py`
  - high severity conflict의 operator queue 누락 여부 검증
  - queue coverage/resolved ratio/ack latency 검증
  - operator note 누락 및 stale feedback 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_source_conflict_operator_feedback.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_SOURCE_CONFLICT_OPERATOR_FEEDBACK=1 ./scripts/test.sh`
