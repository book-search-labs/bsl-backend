# B-0611 — Chat AuthZ Gate v1 (Tool/Write)

## Priority
- P0

## Dependencies
- B-0601
- B-0603
- B-0604

## Goal
Tool 조회/WRITE 실행 전에 권한 검증을 강제해 교차 사용자 데이터 접근 사고를 차단한다.

## Why
- confirmation만으로는 권한 사고를 막을 수 없음
- actor/target/auth context 부재 시 감사/법적 대응 불가

## Scope
### 1) Mandatory auth context
- 모든 tool 호출에 `user_id`, `tenant_id`, `auth_context` 주입
- missing auth context 시 fail-closed

### 2) Policy checks
- actor가 target(order_id 등)에 접근 가능한지 검증
- deny 시 reason_code와 사용자 안내 문구 표준화

### 3) Audit
- `actor`, `target`, `decision`, `policy_rule` 저장

## DoD
- 타인 주문 조회/환불 실행 경로가 전부 차단된다.
- auth context 누락 호출이 100% 차단된다.
- 권한 deny가 표준 reason_code로 기록된다.

## Interfaces
- authz middleware / policy client
- tool execution wrapper

## Observability
- `chat_authz_check_total{result,action}`
- `chat_authz_deny_total{rule}`

## Test / Validation
- cross-user access negative tests
- missing auth context tests
- policy cache miss/fail tests

## Codex Prompt
Enforce authorization at tool/write boundaries:
- Require actor/tenant/auth context on all tool calls.
- Block unauthorized target access with explicit reason codes.
- Persist authorization decisions in audit logs.
