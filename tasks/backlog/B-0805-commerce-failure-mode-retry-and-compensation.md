# B-0805 — Commerce Failure Mode + Retry + Compensation

## Priority
- P0

## Dependencies
- B-0804

## Goal
Commerce MSA 실험의 핵심인 부분 실패, timeout, idempotency 복구, manual retry, cancel compensation을 구현한다.

이 티켓은 "분산 transaction 없이 복구 가능한 checkout"을 검증하는 단계다.

retry와 compensation도 core checkout flow의 일부이므로 HTTP orchestration으로 수행한다. Kafka/outbox는 보상 command 전달 수단이 아니라 정산, 알림, analytics, dashboard, replay, audit 같은 후속 처리 이벤트에만 사용한다.

이 티켓의 recovery 구현은 pivot-aware 해야 한다. 되돌릴 수 있는 step은 backward recovery가 가능하지만, 되돌리기 어렵거나 외부에서 확정된 side effect는 pivot으로 보고 이후 실패를 forward/manual recovery 중심으로 처리한다.

## Scope
### 1) Failure mode APIs
payment-service, inventory-service, shipment-service에 failure mode를 추가한다.

- `POST /internal/admin/failure-mode`
- mode:
  - `SUCCESS`
  - `FAIL_500`
  - `TIMEOUT`
  - `SUCCESS_BUT_TIMEOUT`
  - `RANDOM`

동작:
- `SUCCESS`: 정상 성공
- `FAIL_500`: 500 응답 또는 runtime failure
- `TIMEOUT`: client timeout보다 오래 지연
- `SUCCESS_BUT_TIMEOUT`: DB에는 성공 저장 후 응답 지연
- `RANDOM`: 위 모드 중 하나를 랜덤 적용

Failure mode status policy:
- `TIMEOUT` and `SUCCESS_BUT_TIMEOUT` must be treated as unknown outcome first, not immediate permanent failure.
- orchestrator must store `UNKNOWN` when the side effect may have happened but the response is missing.
- retry/reconciliation must use the same `Idempotency-Key` or downstream lookup API.

### 2) Manual retry API
- checkout-orchestrator:
  - `POST /internal/checkouts/{checkoutId}/steps/{stepName}/retry`
- BFF:
  - `POST /v1/checkout/{checkoutId}/steps/{stepName}/retry`
- `FAILED_RETRYING` 또는 `MANUAL_REVIEW_REQUIRED` step만 다시 `READY`로 전환
- 실패한 step만 재실행 가능
- retry 요청 payload는 최소 `reason`, `operator_id`를 받을 수 있게 설계
- retry action은 audit 대상이며 API response에 변경 전/후 상태를 포함

### 3) Cancel and compensation
- checkout-orchestrator:
  - `POST /internal/checkouts/{checkoutId}/cancel`
- BFF:
  - `POST /v1/checkout/{checkoutId}/cancel`
- 성공한 step을 역순으로 보상:
  - `REQUEST_SHIPMENT` 성공 -> shipment cancel
  - `AUTHORIZE_PAYMENT` 성공 -> payment cancel
  - `RESERVE_STOCK` 성공 -> inventory release
- 각 보상 호출은 checkout-orchestrator가 하위 서비스를 HTTP로 직접 호출한다.
- compensation 성공/실패 이벤트가 필요하면 outbox_event에 후속 처리용으로만 기록한다.
- `CREATE_ORDER`는 1차에서 checkout saga만 `CANCELLED`로 두되, order cancel API가 있으면 연결 가능
- compensation 실패 시 saga `CANCEL_FAILED`

Compensation idempotency rules:
- 모든 compensation call도 `Idempotency-Key`를 사용한다.
- key format:
  - shipment cancel: `checkout:{checkoutId}:REQUEST_SHIPMENT:compensate`
  - payment cancel: `checkout:{checkoutId}:AUTHORIZE_PAYMENT:compensate`
  - inventory release: `checkout:{checkoutId}:RESERVE_STOCK:compensate`
- 같은 compensation key 재호출은 같은 cancellation/release 결과를 반환해야 한다.
- compensation step은 별도 response/error payload를 남겨 운영자가 어떤 보상이 끝났는지 확인 가능해야 한다.

Required recovery/idempotency tests:
- manual retry does not generate a new forward idempotency key
- manual retry only changes the failed step back to `READY`
- manual retry cannot re-run already `SUCCEEDED` steps
- `SUCCESS_BUT_TIMEOUT` followed by retry replays the existing downstream success result without duplicate side effect
- cancel uses only `:compensate` keys and never reuses forward keys
- repeated cancel request replays already completed compensation results when possible
- compensation failure leaves enough persisted state for a later operator retry

### 4) Status policy
- retry 가능 실패: step `FAILED_RETRYING`
- max retry 초과: saga `MANUAL_REVIEW_REQUIRED`
- cancel 진행: saga `CANCELLING`
- cancel 성공: saga `CANCELLED`
- cancel 실패: saga `CANCEL_FAILED`

### 5) Backward recovery trigger policy
- 사용자/운영자 cancel 요청은 backward recovery를 실행한다.
- forward recovery retry 한도 초과 후 운영자가 cancel을 선택하면 backward recovery를 실행한다.
- 비즈니스상 더 이상 진행 불가능한 실패(예: 재고 부족)는 이미 성공한 후속 side effect가 있으면 backward recovery를 실행한다.
- 보상 중 실패하면 추가 자동 보상을 반복하지 않고 `CANCEL_FAILED`로 멈춘다.

### 6) Pivot-aware recovery policy
- step category가 `PIVOT`이고 성공이 확인된 뒤에는 기본적으로 backward compensation을 자동 실행하지 않는다.
- pivot 이후 실패는 1차 forward retry, 2차 `MANUAL_REVIEW_REQUIRED`, 3차 운영 승인 후 reversal/compensation 순서로 처리한다.
- pivot compensation은 rollback이 아니라 cancellation/reversal 같은 별도 업무 transaction으로 모델링한다.
- pivot step이 timeout/unknown이면 compensation 전에 reconciliation을 먼저 수행한다.
- MVP에서 `AUTHORIZE_PAYMENT`는 cancel 가능한 authorization hold로 보아 compensatable하다.
- 추후 payment capture/final charge, real carrier shipment accept, external ledger posting이 추가되면 해당 step은 pivot으로 재분류해야 한다.

## Non-goals
- refund request/approve/process API migration, handled by B-0809
- notification-service 구현
- Kafka relay 연동
- Admin full UI

## Test / Validation
- payment `FAIL_500` -> checkout `FAILED_RETRYING` 또는 `MANUAL_REVIEW_REQUIRED`
- payment `SUCCESS_BUT_TIMEOUT` -> retry 시 같은 payment 반환, 중복 결제 없음
- payment/shipment `TIMEOUT` -> step `UNKNOWN`, reconciliation 이후 `SUCCEEDED` 또는 `FAILED_RETRYING`
- inventory 재고 부족 -> payment cancel compensation 발생
- shipment `TIMEOUT` -> `REQUEST_SHIPMENT` step `FAILED_RETRYING`
- manual retry API는 실패 step만 다시 실행
- manual retry API는 기존 step `Idempotency-Key`를 그대로 재사용
- cancel은 성공 step을 역순 보상
- cancel compensation은 forward key가 아닌 `:compensate` key만 사용
- compensation API 재호출이 idempotent하게 같은 결과를 반환
- compensation 실패 시 saga `CANCEL_FAILED`
- pivot 성공 이후 downstream/internal 후속 실패는 forward retry/manual review로 처리되고 자동 rollback하지 않음
- reversal/compensation이 필요한 pivot 후속 복구는 operator reason/approval context를 요구
- `./scripts/test.sh`

## DoD
- failure mode로 부분 성공/timeout을 재현 가능함
- idempotency로 중복 결제/예약/배송이 방지됨
- manual retry와 cancel compensation이 동작함
- pivot-aware forward/manual recovery가 동작함
- timeout/unknown side effect가 reconciliation 없이 permanent failure나 compensation으로 처리되지 않음
- retry/compensation이 Kafka command 없이 HTTP orchestration으로 동작함
- 운영자가 saga 상태만 보고 다음 조치를 판단할 수 있음

## Codex Prompt
Implement Commerce MSA phase 5:
- Add failure mode APIs to payment, inventory, and shipment services.
- Add checkout step manual retry API.
- Add cancel and compensation flow in checkout-orchestrator.
- Execute retry and compensation through HTTP calls, not Kafka/outbox commands.
- Preserve idempotency on retry, especially SUCCESS_BUT_TIMEOUT.
- Treat timeout as UNKNOWN and add reconciliation before failure/compensation.
- Add pivot-aware recovery: forward retry after pivot, manual review before reversal/compensation.
- Enforce idempotency for compensation calls too.
- Add tests proving retry reuses the original forward key and compensation uses separate `:compensate` keys.
- Require retry/cancel reason and operator audit context.
- Add scenario tests for 500, timeout, success-but-timeout, insufficient stock, retry, and cancel compensation.
