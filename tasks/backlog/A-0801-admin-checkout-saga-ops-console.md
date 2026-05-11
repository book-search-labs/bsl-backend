# A-0801 — Admin Checkout Saga Ops Console

## Priority
- P2

## Dependencies
- B-0804
- B-0805

## Goal
운영자가 checkout saga의 현재 상태, 실패 step, retry 가능 여부, compensation 결과를 Web Admin에서 확인하고 수동 복구할 수 있게 한다.

## Scope
### 1) Admin pages
- Checkout saga list
  - status filter
  - current step
  - updated_at 기준 정렬
  - manual review required 강조
- Checkout saga detail
  - request payload
  - context payload
  - step timeline
  - step category (`COMPENSATABLE`, `PIVOT`, `RETRIABLE`)
  - recovery policy (`BACKWARD`, `FORWARD`, `MANUAL`)
  - `UNKNOWN` and reconciliation status
  - retry count / max retry count
  - last error code/message
  - outbox events
- outbox events are displayed as follow-up domain event records for settlement, notification, analytics, dashboard, replay, and audit inspection

### 2) Admin actions
- failed step retry
- checkout cancel
- compensation result refresh
- unknown step reconciliation retry
- pivot reversal/compensation request with explicit operator reason/approval context
- actions must call BFF, not internal services directly
- actions must execute HTTP orchestration APIs, not Kafka/outbox replay commands
- retry/cancel action form must require an operator reason
- UI must show before/after status after an action completes

### 3) BFF/admin API
- BFF admin route가 checkout-orchestrator internal API로 위임
- Admin RBAC와 audit log를 기존 패턴에 맞춰 적용
- Audit log required fields:
  - `admin_id`
- `action`
  - `checkout_id`
  - `step_name` when applicable
  - `step_category` when applicable
  - `recovery_policy` when applicable
  - `reason`
  - `approval_id` when reversal/compensation after pivot requires approval
  - `before_status`
  - `after_status`
  - `trace_id`
  - `request_id`
  - `created_at`

## Non-goals
- Customer-facing checkout UI redesign
- Full settlement/payment admin redesign
- Kafka DLQ replay UI

## Test / Validation
- list/detail rendering test
- retry button calls BFF endpoint
- cancel button calls BFF endpoint
- retry/cancel without reason is blocked
- pivot reversal/compensation without approval context is blocked
- UNKNOWN reconciliation action calls BFF endpoint and records before/after status
- audit log is written for retry/cancel actions
- forbidden user cannot execute admin recovery action
- `./scripts/test.sh`

## DoD
- 운영자가 실패 checkout을 UI에서 찾을 수 있음
- 실패 step retry와 checkout cancel을 UI에서 실행 가능
- UNKNOWN reconciliation과 pivot/manual recovery 대상이 UI에서 구분됨
- BFF 단일 진입점 원칙이 유지됨
- 운영 action이 Kafka/outbox command replay가 아니라 BFF HTTP API를 통해 수행됨
- 위험 작업은 audit log에 남음

## Codex Prompt
Implement Admin Checkout Saga Ops Console:
- Add Web Admin list/detail pages for checkout saga state.
- Add retry and cancel actions through BFF admin APIs.
- Show step timeline, step category, recovery policy, UNKNOWN/reconciliation state, retry count, errors, context payload, and outbox events.
- Require explicit operator reason/approval for pivot reversal or compensation.
- Treat outbox events as follow-up processing/audit records, not as command replay controls.
- Enforce existing admin RBAC/audit patterns.
- Require operator reason and persist audit log for retry/cancel actions.
