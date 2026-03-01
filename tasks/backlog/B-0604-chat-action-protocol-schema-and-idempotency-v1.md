# B-0604 — Chat Action Protocol v1 (Schema + Idempotency + Audit Fields)

## Priority
- P0

## Dependencies
- B-0601
- B-0603
- B-0611

## Goal
WRITE 액션 실행 계약을 JSON schema로 고정해 검증 가능성과 안전성을 확보한다.

## Why
- 비정형 액션 인자/응답은 실행 오류와 중복 실행 사고를 유발함

## Scope
### 1) Action draft schema
- `action_type`, `args`, `risk_level`, `requires_confirmation`, `idempotency_key`, `expires_at`, `audit_fields`

### 2) Validation
- action별 args schema 등록/검증
- invalid schema는 실행 전 차단 + `chat_bad_action_schema`

### 3) Execution contract
- `dry_run` 지원 (검증만 수행)
- `compensation_hint` 필드 정의

## DoD
- 모든 write action이 공통 스키마를 통과해야 실행된다.
- idempotency_key가 누락된 write action은 reject된다.
- action audit에 actor/target/auth context가 누락 없이 저장된다.

## Interfaces
- action registry
- tool executor contract

## Observability
- `chat_action_validate_total{result,action_type}`
- `chat_action_idempotency_reject_total{action_type}`

## Test / Validation
- schema validation unit tests
- idempotency replay tests
- dry_run integration tests

## Codex Prompt
Define and enforce a strict action protocol:
- Introduce typed action schema per action type.
- Require idempotency and audit fields for write actions.
- Reject invalid action drafts before execution.
