# B-0701 — Chat Contract Freeze + Compatibility Harness

## Priority
- P0

## Dependencies
- B-0391

## Goal
전면 리라이트 동안 외부 API 계약이 깨지지 않도록 `/chat` 계열 응답을 계약 동결(freeze)하고 자동 호환성 게이트를 구축한다.

## Scope
### 1) Contract freeze baseline
- 대상 엔드포인트: `/chat`, `/chat/session/state`, `/chat/session/reset`
- 현재 운영 응답을 golden fixture로 저장(성공/실패/fallback/confirm 케이스)
- 계약 동결 기간 동안 필수 필드 제거 금지

### 2) Compatibility harness
- `contracts/*.schema.json` 기반 JSON Schema 검증 자동화
- golden response snapshot diff(필드/타입/enum/기본값) 검증
- `reason_code`, `next_action`, `recoverable` 변경 감지

### 3) CI gate
- PR 단계에서 contract-compat 스크립트 실패 시 머지 차단
- baseline 갱신은 `--write-baseline` 옵션 + 별도 승인 절차

### 4) Rollback-ready docs
- 계약 위반 시 즉시 legacy 엔진 복귀 절차 문서화
- 운영자용 빠른 체크리스트(runbook) 추가

## Data / Schema
- 기존 `contracts/chat-response.schema.json` 유지
- 계약 변경 필요 시 별도 PR 분리(SSOT 규칙 준수)

## Test / Validation
- schema validation tests
- snapshot diff tests (golden fixtures)
- backward compatibility tests (optional/null field handling)

## DoD
- 리라이트 엔진 응답이 기존 계약 필수 필드를 100% 유지한다.
- 계약 위반이 CI에서 자동 차단된다.
- baseline 갱신 이력이 PR 단위로 추적된다.

## Codex Prompt
Freeze chat API contracts before full rewrite:
- Build schema + snapshot compatibility harness for chat endpoints.
- Block incompatible changes in CI.
- Support controlled baseline refresh with explicit approval.
