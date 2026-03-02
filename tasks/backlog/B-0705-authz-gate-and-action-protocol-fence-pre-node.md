# B-0705 — AuthZ Gate + Action Protocol Fence (Pre-node)

## Priority
- P0

## Dependencies
- B-0703
- B-0704

## Goal
그래프 실행 전 단계에서 Tool/Write 권한과 액션 스키마를 강제 검증해 위험 요청을 조기 차단한다.

## Scope
### 1) Pre-node AuthZ gate
- 모든 tool call에 `user_id`, `tenant_id`, `auth_context` 필수
- actor/target 매칭 검증(교차 사용자 접근 차단)
- 권한 실패 시 노드 실행 전 즉시 deny 응답

### 2) Action protocol validation
- `action_type`, `args(schema)`, `risk_level`, `requires_confirmation`, `idempotency_key` 검증
- invalid args/unknown action type 차단
- write action에 `idempotency_key` 없으면 execute 금지

### 3) Unified deny policy
- deny 응답의 `reason_code` taxonomy 통일
- `next_action` 표준: `LOGIN_REQUIRED` / `OPEN_SUPPORT_TICKET` / `PROVIDE_REQUIRED_INFO`

### 4) Audit requirements
- authz decision 로그에 `actor/target/decision/policy_rule` 기록
- 차단 이벤트 메트릭 집계

## Test / Validation
- cross-user access denial tests
- missing auth context tests
- malformed action payload rejection tests

## DoD
- 권한 없는 Tool/Write 실행이 0건이다.
- action schema 위반이 execute 단계에 도달하지 않는다.
- deny 응답이 공통 reason_code 체계를 따른다.

## Codex Prompt
Add pre-node safety fences for LangGraph rewrite:
- Enforce AuthZ context before any tool/write path.
- Validate action protocol schema and idempotency requirements.
- Block early with unified reason codes and audit records.
