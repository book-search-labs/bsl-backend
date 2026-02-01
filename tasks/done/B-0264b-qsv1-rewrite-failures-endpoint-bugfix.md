# File: tasks/backlog/B-0264b-qsv1-rewrite-failures-endpoint-bugfix.md

# B-0264b — QS: /internal/qc/rewrite/failures endpoint bugfix

## Goal
`GET /internal/qc/rewrite/failures`에서 undefined `analysis` 참조로 500이 발생하는 문제를 수정하고,
SQLite rewrite_log 기반으로 실패 이벤트를 안정적으로 조회할 수 있게 한다.

## Current State
- QS는 rewrite 이벤트를 SQLite로 로그(rewrite_log)하는 뼈대가 있음.
- `/internal/qc/rewrite/failures`가 존재하지만 routes에서 undefined 변수 참조(버그)로 동작 불안정.

## Scope
- endpoint 구현을 rewrite_log(SQLite) 쿼리로 재정의:
  - failure rows 반환 (최근순)
  - query params: `limit`, `since`, `reason`(optional)
- 빈 DB/파일 없음/권한 문제에서도 안전하게 처리(가능한 200 + 빈 배열 or 명확한 에러)

## Non-goals
- UI(Admin Playground) 연동은 별도 티켓(A-0124)에서 수행
- rewrite 품질 개선(LLM/T5)은 별도 티켓에서 수행

## Interfaces
- Endpoint: `GET /internal/qc/rewrite/failures`
- Query params (proposed):
  - `limit` (default 50, max 500)
  - `since` (ISO datetime or epoch; optional)
  - `reason` (optional)
- Response:
  - `items: [ {ts, request_id, q_raw?, q_norm?, reason, strategy, success, error_code?, error_message?} ]`

## DoD
- endpoint가 200으로 정상 응답한다.
- `limit` 동작 및 max clamp 동작.
- rewrite_log DB가 비어있어도 200 + empty list.
- Unit test/E2E test 추가:
  - empty DB 케이스
  - sample rows insert 후 조회 케이스

## Files to Change
- `services/query-service/app/api/routes.py`
- `services/query-service/app/core/rewrite_log.py` (조회 함수 없으면 추가)
- `services/query-service/tests/...`

## Commands
- `cd services/query-service`
- `pytest -q`

## Notes
- SQLite path: `QS_REWRITE_DB_PATH` (default `/tmp/qs_rewrite.db`)
- 운영에서는 BFF/observability trace와 연결될 수 있도록 `request_id/trace_id` 포함 권장.

## Codex Prompt
Fix /internal/qc/rewrite/failures so it does not reference undefined variables and returns failure records from rewrite_log SQLite.
Add tests for empty and non-empty DB cases.
Keep changes minimal.
