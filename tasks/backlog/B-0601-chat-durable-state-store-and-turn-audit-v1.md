# B-0601 — Chat Durable State Store + Turn/Audit Ledger v1

## Priority
- P0

## Dependencies
- B-0391 (chat production launch readiness gate)
- I-0362 (data governance retention/egress)

## Goal
캐시 중심 세션 상태를 DB 기반 durable state로 전환해 멀티턴 재현성, 동시성 안전성, 감사 추적성을 확보한다.

## Why
- 현재 세션 상태가 메모리/캐시에 편중되어 복구/재현/감사 대응이 약함
- `state_version`/`idempotency_key`/`turn_event`가 없으면 오실행 원인 추적이 어려움

## Scope
### 1) 상태 저장소 스키마
- `chat_session_state` 도입: `conversation_id`, `user_id`, `state_version`, `last_turn_id`, `pending_action`, `selection`, `summary_short`, `expires_at`
- `chat_turn_event` 도입: turn input/output, route, reason_code, trace/request id, latency
- `chat_action_audit` 도입: actor/target/action/result/auth_context/idempotency_key

### 2) 상태 업데이트 계약
- optimistic lock(`state_version`) 강제
- 동일 `idempotency_key` 중복 turn/action 재실행 차단
- `last_turn_id` 기반 out-of-order turn 감지

### 3) 운영 연결
- 모든 경로에서 `trace_id`, `request_id`, `reason_code` 필수 적재
- 실패 turn 포함 append-only 이벤트 기록

## Non-goals
- 추천 알고리즘 개선
- UI 리뉴얼

## DoD
- 동시 요청 충돌 시 stale write가 차단된다.
- 재시도/중복 전송에도 action 중복 실행이 발생하지 않는다.
- 임의 세션 1건에 대해 turn/event/audit replay가 가능하다.
- retention/TTL 정책이 적용된다.

## Interfaces
- `POST /v1/chat`
- `POST /v1/chat/actions/*`
- `GET /v1/chat/session-state`

## Observability
- `chat_state_conflict_total`
- `chat_state_write_total{result}`
- `chat_turn_event_append_total{result}`

## Test / Validation
- 동시 업데이트 race test
- idempotency replay test
- state_version mismatch integration test
- session replay snapshot test

## Codex Prompt
Implement durable state storage for chat:
- Add chat session/turn/audit tables and optimistic lock semantics.
- Enforce idempotency and ordered turn updates.
- Persist reason codes and tracing fields for replay/debug.
