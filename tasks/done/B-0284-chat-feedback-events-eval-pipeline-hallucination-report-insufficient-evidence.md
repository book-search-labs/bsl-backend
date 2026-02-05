# B-0284 — Chat Feedback 이벤트 + 평가 파이프라인(👍👎/환각/근거부족) → 개선 루프

## Goal
RAG 챗봇 품질을 “운영 루프”로 닫는다.

- 사용자 피드백(👍👎, hallucination 신고, 근거부족)을 이벤트로 수집
- 재현 가능한 단위로 저장:
  - 질문, 사용된 chunk_id, 모델버전, 답변, citations
- 오프라인 평가/회귀세트로 전환 가능한 데이터셋을 만든다.

## Background
- RAG 품질 개선의 핵심은 “실패 케이스 큐레이션”
- 특히 “근거부족/환각 의심”을 모으면 다음 개선이 빨라진다.

## Scope
### 1) Event schema (Kafka 권장)
- `chat_turn` (분모): 질문, 사용 chunk, 모델, latency, degraded 여부
- `chat_feedback`:
  - type: UP/DOWN/HALLUCINATION/NO_CITATION/IRRELEVANT
  - optional: free-text comment
  - include: request_id, session_id, turn_id

### 2) Storage (OLAP or DB)
- 최소 DB 테이블:
  - `chat_turn(turn_id, request_id, session_id, q, answer, citations_json, used_chunks_json, model_version, created_at)`
  - `chat_feedback(feedback_id, turn_id, feedback_type, comment, created_at)`
- 또는 Kafka→OLAP(ClickHouse/BigQuery) 적재(I-0305 연계)

### 3) Triage pipeline (필수)
- “실패 큐” 생성:
  - DOWN or HALLUCINATION 비율 높은 turn 모아보기
- 샘플링:
  - 최근 7일 + top queries

### 4) Metrics
- helpful_rate(UP/(UP+DOWN))
- hallucination_report_rate
- no_citation_rate(should be ~0 if 강제 성공)

## Non-goals
- Admin 라벨링 UI(A-0123) (별도 티켓)
- 자동 평가 LLM-judge (후속 확장)

## DoD
- User Web에서 피드백 전송 가능
- 이벤트가 Kafka(또는 outbox)로 발행됨
- turn/feedback이 저장되고 재현 정보 포함
- 기본 집계 지표 3개가 대시보드로 뽑히는 수준(간단 로그 기반도 OK)

## Codex Prompt
Implement chat feedback loop:
- Define chat_turn and chat_feedback schemas and emit events (prefer Kafka via outbox).
- Persist turns and feedback with reproducible metadata (used_chunks, citations, model_version).
- Add basic aggregation queries/metrics for helpful rate and hallucination reports.
