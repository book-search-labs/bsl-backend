# B-0385 — Chat Resolution Knowledge Ingestion from Closed Tickets

## Priority
- P2

## Dependencies
- B-0370, B-0376, B-0381

## Goal
해결 완료된 티켓의 유효 해결지식을 챗봇 지식베이스로 반영해 동일 문제 재문의를 줄인다.

## Scope
### 1) Ingestion criteria
- closed ticket 중 재사용 가능한 해결 패턴 선별 규칙
- 민감정보/개인정보 제거 규칙

### 2) Knowledge structuring
- 문제유형, 해결절차, 제한조건, 적용범위를 구조화
- source provenance(티켓ID/승인자/승인시각) 기록

### 3) Approval pipeline
- 자동 후보 생성 -> 운영 승인 -> 지식베이스 반영
- 반영 후 성능 모니터링 및 rollback

### 4) Retrieval integration
- 유사 이슈 질의에 우선 추천
- 오래된 해결지식 만료/재검증 루프

## Observability
- `chat_ticket_knowledge_candidate_total`
- `chat_ticket_knowledge_approved_total`
- `chat_ticket_knowledge_hit_total`
- `chat_ticket_knowledge_rollback_total`

## Test / Validation
- 후보 선별 정확성 테스트
- PII 제거/익명화 테스트
- 반영 전/후 반복문의 감소 지표 검증

## DoD
- 반복 이슈 대응 속도 향상
- 승인되지 않은 티켓지식 미반영 보장
- 지식 반영/롤백 이력 감사 가능

## Codex Prompt
Close the loop from support tickets to chat knowledge:
- Extract reusable resolutions from closed tickets with privacy scrubbing.
- Require operator approval before indexing into retrieval.
- Track impact on repeat-issue resolution and allow rollback.
