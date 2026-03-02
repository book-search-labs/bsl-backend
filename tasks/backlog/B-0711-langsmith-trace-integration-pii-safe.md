# B-0711 — LangSmith Trace Integration (PII-safe)

## Priority
- P1

## Dependencies
- B-0703
- B-0612

## Goal
LangGraph 실행을 LangSmith에 노드 단위로 추적하되, 개인정보가 외부 추적 시스템으로 유출되지 않도록 PII-safe 전송 체계를 구축한다.

## Scope
### 1) Trace adapter
- 그래프 run 시작/종료/노드 실행 이벤트를 LangSmith run으로 전송
- metadata: `trace_id`, `request_id`, `session_id`, `route`, `reason_code`, `state_version`

### 2) PII redaction before export
- 기존 redaction 규칙을 trace payload에도 적용
- 원문 message/body는 정책 모드에 따라 `masked_raw` 또는 `hash+summary`

### 3) Sampling and controls
- tenant/channel 기반 trace sample rate 설정
- 장애 시 tracing off 가능한 kill switch 제공

### 4) Ops visibility
- run 링크를 내부 로그와 연결
- 노드 실패/재시도/차단 reason drill-down 제공

## Test / Validation
- tracer adapter unit tests
- redaction conformance tests
- sample rate behavior tests

## DoD
- 주요 경로의 그래프 실행이 LangSmith에서 추적 가능하다.
- PII 누출 없이 추적 데이터가 전송된다.
- trace disabled/sampling 제어가 운영 환경에서 동작한다.

## Codex Prompt
Integrate LangSmith for LangGraph runs safely:
- Emit node-level traces with route/reason metadata.
- Apply PII masking before export.
- Add runtime sampling and kill-switch controls.
