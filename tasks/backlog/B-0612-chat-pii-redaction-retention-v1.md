# B-0612 — Chat PII Redaction + Retention v1

## Priority
- P0

## Dependencies
- B-0601
- I-0362

## Goal
대화/감사 로그 저장 시 PII 유출을 차단하고 보존 정책을 시스템적으로 강제한다.

## Why
- 원문 로그 적재는 주소/전화/결제식별자 유출 사고로 직결됨

## Scope
### 1) Redaction policy
- 주소/전화/이메일/결제 식별자 마스킹 규칙 공통화
- `message_text` 저장 모드 분리: `masked_raw` 또는 `hash+summary`

### 2) Access control
- 로그 조회 RBAC
- 민감 필드 read scope 분리

### 3) Retention
- turn/event/audit 별 TTL
- 삭제 잡 및 삭제 감사 로그

## DoD
- 금지 PII 패턴이 평문으로 저장되지 않는다.
- 저장 모드 정책이 환경별로 강제된다.
- retention 만료 데이터가 자동 삭제된다.

## Interfaces
- logging pipeline
- data retention jobs

## Observability
- `chat_pii_redaction_total{field_type}`
- `chat_log_access_denied_total{scope}`
- `chat_retention_delete_total{table}`

## Test / Validation
- redaction unit tests (pattern set)
- RBAC integration tests
- retention job e2e tests

## Codex Prompt
Add privacy-safe logging policy for chat:
- Apply field-level PII redaction before persistence.
- Support masked/raw vs hash+summary storage modes.
- Enforce retention and access controls with auditability.
