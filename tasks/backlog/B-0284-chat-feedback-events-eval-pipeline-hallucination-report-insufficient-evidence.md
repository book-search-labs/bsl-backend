# B-0284 — Chat Feedback Event + Assessment Pipeline → Improved Loop

## Goal
RAG chat bot quality close to “operate loop”.

- Collect user feedback
- Storage with reproducible unit:
  - Question, used chunk id, model version, answer, citations
- We use cookies to give you the best experience on our website. If you continue to use this site we will assume that you are happy with it.Ok

## Background
- The core of RAG quality improvement “Secret Case Curation”
- In particular, if you want to know the “commuting/returning suspicious”, then the improvement will be sucked.

## Scope
### 1) Event schema (Kafka recommended)
- New TBD (분모): Question, use chunk, model, latency, degraded or
- `chat_feedback`:
  - type: UP/DOWN/HALLUCINATION/NO_CITATION/IRRELEVANT
  - optional: free-text comment
  - include: request_id, session_id, turn_id

### 2) Storage (OLAP or DB)
- Minimum DB table:
  - `chat_turn(turn_id, request_id, session_id, q, answer, citations_json, used_chunks_json, model_version, created_at)`
  - `chat_feedback(feedback_id, turn_id, feedback_type, comment, created_at)`
- or Kafka→OLAP(ClickHouse/BigQuery) loading(I-0305 connection)

### Triage pipeline (required)
- Create “Secret Cut”:
  - DOWN or HALLUCINATION rate High turn View
- Sample:
  - Last 7 days + top queries

### 4) Metrics
- helpful_rate(UP/(UP+DOWN))
- hallucination_report_rate
- no citation rate(should be ~0 if forced success)

## Non-goals
- Admin Labeling UI(A-0123) (Annex Ticket)
- Automatic evaluation LLM-judge (reverse expansion)

## DoD
- User Web
- Event is issued by Kafka (or outbox)
- turn/feedback
- 3 basic aggregate indicators are selected as a dashboard (simple log-based OK)

## Codex Prompt
Implement chat feedback loop:
- Define chat_turn and chat_feedback schemas and emit events (prefer Kafka via outbox).
- Persist turns and feedback with reproducible metadata (used_chunks, citations, model_version).
- Add basic aggregation queries/metrics for helpful rate and hallucination reports.
