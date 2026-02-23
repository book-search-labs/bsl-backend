# B-0380 — Chat Effective-date-aware Policy Answering

## Priority
- P1

## Dependencies
- B-0365, B-0377, B-0368

## Goal
정책/공지/이벤트 변경 시점(적용 시작/종료일)을 인지해, 질문 시점에 맞는 정답을 반환하도록 챗봇의 시간 인식 추론을 강화한다.

## Non-goals
- 자연어 전체 시계열 추론 엔진을 일반 목적용으로 구현하지 않는다.
- 정책 원문 작성 시스템 자체를 대체하지 않는다.

## Scope
### 1) Temporal metadata model
- 문서에 `effective_from`, `effective_to`, `announced_at` 메타데이터 표준화
- 시점 미기재 문서의 기본 규칙 정의

### 2) Query-time temporal filtering
- 사용자 질문의 기준일(오늘/과거/특정일) 해석
- 해당 시점에 유효한 문서 우선 retrieval

### 3) Answer rendering
- 답변에 적용 기준일/정책 버전 표시
- 시점 불명확 시 추가 질문으로 보완

### 4) Conflict + fallback
- 유효기간 중첩/충돌 시 safe abstention 적용
- 공식 출처 확인 링크 제공

## Data / Schema
- `chat_policy_temporal_meta` (new): source_id, effective_from, effective_to, announced_at, timezone
- `chat_temporal_resolution_audit` (new): request_id, reference_time, matched_source_ids, resolution_strategy
- 계약(`contracts/`) 변경이 필요하면 별도 PR로 분리

## Interfaces
- `POST /v1/chat`
- `GET /internal/chat/policy/temporal/{sourceId}`
- `POST /internal/chat/policy/temporal/resolve`

## Observability
- `chat_temporal_policy_match_total{result}`
- `chat_temporal_disambiguation_total`
- `chat_temporal_conflict_total`
- `chat_temporal_answer_with_effective_date_total`
- `chat_temporal_reference_parse_error_total`

## Test / Validation
- 시점별 정책 정답셋 회귀 테스트
- 상대시각("오늘/어제/내일") 해석 테스트
- 유효기간 충돌 시 fallback 테스트
- 타임존(Asia/Seoul 기준) 경계 시간 테스트

## DoD
- 정책 변경 시점 오답률 감소
- 답변 기준일/버전의 투명성 확보
- 시점 애매 질의에서 추가질문 일관성 확보
- 기준시각 파싱/적용 로그로 운영자가 재현 가능

## Codex Prompt
Add temporal reasoning to policy answers:
- Use effective date metadata in retrieval and synthesis.
- Resolve user time references and surface policy effective windows.
- Apply safe fallback when temporal ambiguity or conflicts remain.
