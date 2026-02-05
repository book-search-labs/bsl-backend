# File: tasks/backlog/B-0266-qsv1-2pass-rewrite-llm-implementation.md

# B-0266 — QS: Implement real LLM rewrite for /query/enhance (JSON schema enforced)

## Goal
`POST /query/enhance`에서 REWRITE 전략이 선택되었을 때 placeholder(no-op)가 아니라
실제 LLM rewrite가 동작하도록 한다. 출력은 JSON 스키마로 강제한다.

## Current State
- enhance gating/캐시/예산제는 구현됨.
- rewrite/spell/RAG rewrite 로직은 placeholder.
- rewrite 이벤트를 SQLite에 남기는 뼈대가 있음.

## Scope
- LLM 호출 경로:
  - 우선: LLM Gateway(B-0283) 존재 시 그쪽 HTTP 호출
  - 없으면 QS 내부 최소 구현(환경변수로 provider 선택)
- JSON schema 강제:
  - `{ q_rewrite: string, confidence: number, intent?: string, slots?: object }`
- validation:
  - non-empty string, max length
  - prohibited output (답변 생성 금지, 설명문 금지)
  - injection 흔적 방어(간단 룰)
- 실패 시 degrade: 원문 유지 + reason_codes

## Non-goals
- RAG rewrite는 별도 티켓(B-0267)
- 고급 prompt 튜닝/대규모 eval은 범위 아님(최소 동작 구현)

## Interfaces
- `/query/enhance` response:
  - `rewrite.q_rewrite`, `rewrite.method`, `rewrite.confidence`
  - `final.q_final` 및 `final.strategy`(기존 구조 유지)

## DoD
- REWRITE_ONLY 또는 SPELL_THEN_REWRITE에서 실제 rewrite 수행 가능
- invalid JSON / timeout / rate limit 시 degrade
- rewrite_log(SQLite)에 성공/실패 기록(에러코드 포함)
- metrics:
  - `qs_rewrite_attempt_total`, `qs_rewrite_applied_total`, `qs_rewrite_failed_total`
- tests:
  - provider mock으로 deterministic 테스트
  - invalid json, timeout, empty output 케이스 포함

## Files to Change
- `services/query-service/app/core/enhance.py`
- `services/query-service/app/core/rewrite.py` (new) or existing placeholder
- `services/query-service/app/core/rewrite_log.py`
- tests
- (optional) contracts updates

## Commands
- `cd services/query-service && pytest -q`

## Codex Prompt
Implement LLM-based rewrite for QS enhance with strict JSON schema validation.
Log outcomes to rewrite_log SQLite, add metrics, and add deterministic tests using mocks.
