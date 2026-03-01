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
