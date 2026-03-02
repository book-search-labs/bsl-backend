# B-0706 — Durable Checkpoint + Deterministic Replay Kit

## Priority
- P0

## Dependencies
- B-0703
- B-0704
- B-0350

## Goal
LangGraph 실행의 중간 상태를 durable checkpoint로 저장하고, 장애 재현을 deterministic replay로 자동화한다.

## Scope
### 1) Checkpoint store
- graph step별 checkpoint 저장(`run_id`, `node`, `state_hash`, `updated_at`)
- resume 가능한 최소 상태 필드 저장
- TTL/retention 정책 적용

### 2) Replay payload standard
- `trace_id/request_id/session_id/input/policy_decision/tool_stub_seed` 저장
- 외부 의존 호출 결과를 stub 모드로 재생할 수 있는 payload format 정의

### 3) Replay execution
- 운영자가 replay 요청 가능한 internal endpoint 또는 스크립트 제공
- replay 결과와 원본 결과 diff 리포트 생성

### 4) Observability integration
- replay 성공/실패/불일치 지표
- `replay_id`로 로그/메트릭/감사로그 교차 추적

## Interfaces
- `POST /internal/chat/replay` (or equivalent script)
- `GET /internal/chat/replay/{replay_id}`

## Test / Validation
- deterministic replay tests (same input => same output)
- checkpoint resume tests (interrupt 이후 재개)
- replay diff validation tests

## DoD
- 장애 케이스를 `request_id` 기준 1회 내 재현 가능하다.
- replay 결과와 원본 차이가 자동 보고된다.
- checkpoint 기반 재개가 실서비스 경로에서 동작한다.

## Codex Prompt
Implement durable checkpoints and deterministic replay for LangGraph:
- Persist node-level checkpoints and replay payloads.
- Add replay runner with stubbed dependency mode.
- Produce replay-vs-original diff artifacts for incident triage.
