# B-0802 — Checkout Orchestrator Saga Schema + Start API

## Priority
- P0

## Dependencies
- B-0801

## Goal
checkout-orchestrator-service에 checkout saga 원장을 도입하고, checkout 시작/조회 API를 실제 DB 기반으로 구현한다.

이 단계는 saga 실행 전 단계다. checkout 요청을 받으면 saga와 step 4개를 같은 transaction에 생성하고, 중복 `checkout_key` 요청은 기존 saga를 반환한다.

## Scope
### 0) Communication model boundary
- 이 티켓의 checkout 시작 API는 HTTP orchestration entrypoint다.
- `POST /internal/checkouts`는 Kafka/outbox consumer 완료를 기다리지 않고 즉시 가능한 saga 상태를 반환한다.
- `outbox_event`는 정산, 알림, analytics, dashboard projection, replay, audit 같은 후속 처리용 domain event 저장소다.
- `outbox_event`를 checkout step 실행 command queue로 사용하지 않는다.
- orchestrator local transaction은 saga/step/outbox 원장만 보호하며, payment/inventory 같은 owning service의 자원 invariant를 대신 보장하지 않는다.
- partial state는 정상 상태로 취급한다. workflow 중간 성공/실패/불명확 상태는 `checkout_saga_step`에 추적 가능하게 남긴다.

### 1) Database schema
- checkout-orchestrator DB migration 추가
- `checkout_saga`
  - `id`, `checkout_key`, `user_id`, `status`, `current_step`
  - `request_payload`, `context_payload`
  - `error_code`, `error_message`, `version`
  - `created_at`, `updated_at`
  - unique `checkout_key`
  - index `(status, updated_at)`
- `checkout_saga_step`
  - `id`, `checkout_saga_id`, `step_name`, `status`
  - `step_category` (`COMPENSATABLE`, `PIVOT`, `RETRIABLE`)
  - `recovery_policy` (`BACKWARD`, `FORWARD`, `MANUAL`)
  - `idempotency_key`, `request_payload`, `response_payload`
  - `retry_count`, `max_retry_count`, `next_retry_at`
  - `error_code`, `error_message`, `started_at`, `completed_at`
  - `external_reference_type`, `external_reference_id` for external side-effect reconciliation when available
  - unique `(checkout_saga_id, step_name)`
  - unique `idempotency_key`
  - index `(status, next_retry_at)`
- `outbox_event`
  - domain event publication table for future Outbox Relay/Kafka expansion
  - follow-up processing use cases: settlement, notification, analytics, dashboard projection, replay, audit
  - do not use it as the worker command queue or as a prerequisite for the user-facing checkout response

### 2) Internal APIs
- `POST /internal/checkouts`
  - required: `checkout_key`, `user_id`, `items`, `payment`, `shipping_address`
  - creates saga with status `PENDING`
  - creates steps:
    - `CREATE_ORDER`: `COMPENSATABLE`, recovery `BACKWARD`
    - `RESERVE_STOCK`: `COMPENSATABLE`, recovery `BACKWARD`
    - `AUTHORIZE_PAYMENT`: `COMPENSATABLE` for MVP authorization/void model, but becomes `PIVOT` if changed to capture/final charge
    - `REQUEST_SHIPMENT`: `RETRIABLE` or `PIVOT` depending on carrier API semantics; MVP mock request is retriable/idempotent
  - writes `CHECKOUT_STARTED` outbox event for follow-up consumers only
  - returns the immediate available checkout state without waiting for Outbox Relay/Kafka
- `GET /internal/checkouts/{checkoutId}`
  - returns saga, steps, context, and current status

### 3) Idempotency at orchestrator boundary
- `checkout_key` unique constraint prevents duplicate checkout saga creation
- same `checkout_key` returns the existing checkout response

### 4) Status model and allowed transitions
Saga status:
- `PENDING`
- `PROCESSING`
- `SUCCEEDED`
- `FAILED_RETRYING`
- `MANUAL_REVIEW_REQUIRED`
- `CANCELLING`
- `CANCELLED`
- `CANCEL_FAILED`

Step status:
- `READY`
- `PROCESSING`
- `SUCCEEDED`
- `UNKNOWN`
- `FAILED_RETRYING`
- `MANUAL_REVIEW_REQUIRED`
- `COMPENSATING`
- `COMPENSATED`
- `SKIPPED`

Allowed step transitions:
- create: none -> `READY`
- execute start: `READY` -> `PROCESSING`
- success: `PROCESSING` -> `SUCCEEDED`
- timeout/uncertain side effect: `PROCESSING` -> `UNKNOWN`
- reconciliation success: `UNKNOWN` -> `SUCCEEDED`
- reconciliation retryable failure: `UNKNOWN` -> `FAILED_RETRYING`
- reconciliation exhausted: `UNKNOWN` -> `MANUAL_REVIEW_REQUIRED`
- retryable failure: `PROCESSING` -> `FAILED_RETRYING`
- retry exhausted: `FAILED_RETRYING` -> `MANUAL_REVIEW_REQUIRED`
- manual retry: `FAILED_RETRYING` -> `READY`
- manual unknown reconciliation retry: `UNKNOWN` -> `PROCESSING`
- manual recovery retry: `MANUAL_REVIEW_REQUIRED` -> `READY`
- compensation start: `SUCCEEDED` -> `COMPENSATING`
- compensation success: `COMPENSATING` -> `COMPENSATED`

Allowed saga transitions:
- create: none -> `PENDING`
- worker start: `PENDING` -> `PROCESSING`
- all steps succeeded: `PROCESSING` -> `SUCCEEDED`
- retryable step failed: `PROCESSING` -> `FAILED_RETRYING`
- retry exhausted: `FAILED_RETRYING` -> `MANUAL_REVIEW_REQUIRED`
- manual retry accepted: `FAILED_RETRYING` -> `PROCESSING`
- manual review retry accepted: `MANUAL_REVIEW_REQUIRED` -> `PROCESSING`
- cancel requested: `PENDING|PROCESSING|FAILED_RETRYING|MANUAL_REVIEW_REQUIRED|SUCCEEDED` -> `CANCELLING`
- cancel succeeded: `CANCELLING` -> `CANCELLED`
- cancel failed: `CANCELLING` -> `CANCEL_FAILED`

### 5) Outbox event contract draft
`outbox_event.payload`는 최소 아래 공통 필드를 포함한다.

```json
{
  "event_version": "v1",
  "checkout_id": 1,
  "checkout_key": "user:101:cart:abc:attempt:1",
  "user_id": "101",
  "status": "PENDING",
  "current_step": null,
  "trace_id": "string",
  "request_id": "string",
  "occurred_at": "2026-05-07T00:00:00Z"
}
```

초기 이벤트:
- `CHECKOUT_STARTED`

`event_key`는 `checkout:{checkoutId}:{eventType}:v1` 형식으로 잡고 unique는 후속 티켓에서 필요 시 추가한다.

## Non-goals
- Step execution worker
- HTTP calls to order/payment/inventory/shipment
- retry/cancel/compensation implementation
- 하위 서비스 DB 구현

## Transaction Boundary
- `POST /internal/checkouts`는 saga/step/outbox 생성만 단일 local transaction으로 처리
- 외부 HTTP call은 이 티켓에서 발생하지 않음
- global transaction은 사용하지 않는다. 각 downstream owning service의 local transaction이 자기 resource invariant를 보호해야 한다.
- `checkout_saga_step.step_category`와 `recovery_policy`는 worker가 실패 시 backward/forward/manual recovery를 선택하는 기준이다.

## Test / Validation
- checkout 생성 시 saga + 4개 step + `CHECKOUT_STARTED` outbox event 저장
- 같은 `checkout_key` 재요청 시 기존 saga 반환
- 생성된 step마다 `step_category`, `recovery_policy`, `idempotency_key`가 채워짐
- 상태 enum과 allowed transition validation test
- `UNKNOWN` 상태와 reconciliation transition validation test
- `CHECKOUT_STARTED` payload 필수 필드 검증
- 잘못된 payload validation test
- `./scripts/test.sh`

## DoD
- checkout-orchestrator가 DB 기반 checkout 시작/조회 API를 제공함
- saga와 step 상태가 조회 가능함
- outbox_event가 후속 처리 domain event 용도로만 설계됨
- checkout 진행은 HTTP orchestration으로 설계되고 outbox/Kafka command 처리에 의존하지 않음
- worker 구현 전에도 API가 deterministic하게 동작함

## Codex Prompt
Implement Commerce MSA phase 2:
- Add checkout-orchestrator migrations for checkout_saga, checkout_saga_step, and outbox_event.
- Implement `POST /internal/checkouts` and `GET /internal/checkouts/{checkoutId}`.
- Create saga, four steps, and CHECKOUT_STARTED follow-up outbox event in one short transaction.
- Return existing checkout for duplicate checkout_key.
- Add explicit saga/step status enums and allowed transition guards.
- Add step category/recovery policy metadata and UNKNOWN/reconciliation transitions.
- Use the outbox event payload shape from this ticket.
- Keep outbox/Kafka out of the core checkout command flow.
- Do not implement worker or downstream service calls yet.
