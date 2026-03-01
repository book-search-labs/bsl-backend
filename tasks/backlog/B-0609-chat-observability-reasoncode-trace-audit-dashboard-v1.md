# B-0609 — Chat Observability v1 (Reason Code/Trace/Audit Dashboard)

## Priority
- P1

## Dependencies
- B-0601
- B-0603
- B-0605
- B-0613
- B-0614

## Goal
상태/정책/실행 전 단계를 trace+reason_code로 연결해 원인 분석 시간을 단축한다.

## Why
- 인터랙션 에이전트는 장애 원인이 분산되어 trace 일관성이 없으면 복구가 늦어짐

## Scope
### 1) Telemetry standard
- 모든 단계에 `trace_id`, `request_id`, `reason_code`, `state_version`
- action 실행은 actor/target/result와 연결

### 2) Unified taxonomy
- `NEED_SLOT:*`, `ROUTE:*`, `DENY_EXECUTE:*`, `TOOL_FAIL:*`, `FALLBACK:*`
- 분류 표준을 docs/runbook에 고정

### 3) Ops dashboard
- route 분포, block 원인, confirm 전이, tool 실패, 비용 추이
- trace drill-down 링크

## DoD
- 단일 trace로 route->action->response를 역추적 가능
- reason_code가 미분류(`unknown`) 없이 집계된다.
- 주요 장애 유형의 MTTR이 기준 대비 단축된다.

## Interfaces
- metrics/log schema
- ops dashboard panels

## Observability
- `chat_reason_code_total{reason_code}`
- `chat_trace_link_total{stage}`

## Test / Validation
- telemetry field presence tests
- reason_code taxonomy lint tests
- dashboard query smoke tests

## Codex Prompt
Standardize chat observability across all stages:
- Propagate trace/request IDs and reason codes end-to-end.
- Enforce a shared reason-code taxonomy.
- Build dashboards for route, failure, and action-state analysis.
