# B-0364 — Tool Schema Registry + Permission Policy

## Priority
- P1

## Dependencies
- B-0351

## Goal
챗봇에서 사용하는 tool을 스키마/권한/버전으로 관리해 안전성과 확장성을 확보한다.

## Scope
### 1) Tool registry
- tool name, version, input/output schema
- required auth scope, rate limit class, timeout class

### 2) Permission policy
- user/admin/system caller별 허용 tool 매트릭스
- 민감 tool에 정책 승인 단계(optional)

### 3) Runtime validation
- tool call 전 input schema 검증
- tool response schema 검증 실패 시 격리 처리

### 4) Change management
- breaking change는 v2 스키마로 분리
- registry 변경 이력 감사 로그

## DoD
- 모든 tool call이 registry 스키마 검증을 통과해야 실행
- 무권한 tool 호출 차단
- tool 버전 롤백 가능

## Codex Prompt
Create a tool schema registry:
- Register tool versions, I/O schemas, auth scopes, and runtime limits.
- Validate all tool calls/responses against schemas.
- Enforce permission matrix and versioned rollout/rollback.
