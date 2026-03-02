# B-0702 — LangGraph State Schema v1

## Priority
- P0

## Dependencies
- B-0701

## Goal
LangGraph 전환의 기반이 되는 단일 상태 스키마(`ChatGraphState`)를 정의해 노드 간 데이터 계약을 명확히 한다.

## Scope
### 1) Typed state definition
- 필수 필드: `trace_id`, `request_id`, `session_id`, `query`
- 핵심 필드: `user_id`, `intent`, `route`, `reason_code`, `selection`, `pending_action`, `tool_result`, `response`
- optional/null 허용 규칙 명세

### 2) State versioning
- `state_version` 및 schema version 필드 도입
- 호환성 정책: additive 변경 우선, breaking 변경은 v2 분리

### 3) Validation layer
- 그래프 노드 입/출력마다 schema validation 적용
- invalid state는 즉시 fallback + audit reason_code 기록

### 4) Mapping adapter
- 기존 `chat_session_state` 구조와 상호 변환 어댑터 제공
- selection/pending_action 동기화 규칙 명시

## Data / Schema
- `services/query-service/app/core/chat_graph/state.py` (new)
- `chat_session_state`와 호환 어댑터 추가

## Test / Validation
- state validation unit tests
- missing/invalid field rejection tests
- legacy state -> graph state mapping tests

## DoD
- 모든 노드가 `ChatGraphState`만 읽고 쓴다.
- 잘못된 상태 입력 시 deterministic한 에러/사유코드가 반환된다.
- legacy state와 그래프 state 간 변환 회귀 테스트가 통과한다.

## Codex Prompt
Define LangGraph state schema for chat rewrite:
- Create typed state contract with versioning and validation.
- Add adapters between legacy session state and graph state.
- Enforce node I/O validation across the graph.
