# B-0804 — Checkout Saga Worker + Step Execution

## Priority
- P0

## Dependencies
- B-0802
- B-0803

## Goal
checkout-orchestrator-service에 DB polling saga worker를 구현해 checkout step을 순서대로 실행한다.

중요 원칙은 HTTP call을 DB transaction 밖에서 실행하는 것이다. 각 step은 짧은 상태 변경 transaction, 외부 HTTP call, 짧은 결과 저장 transaction으로 분리한다.

Core checkout flow는 HTTP orchestration이다. checkout-orchestrator가 order/payment/inventory/shipment를 HTTP로 호출해 saga를 진행하며, Kafka/outbox는 step 실행 trigger나 command delivery로 사용하지 않는다.

## Scope
### 0) Core flow communication model
- checkout step 진행은 checkout-orchestrator의 DB polling worker와 downstream HTTP call로 수행한다.
- 사용자/BFF 응답은 Kafka consumer 완료를 기다리지 않고 즉시 가능한 saga 상태를 반환한다.
- 즉시 가능한 결과는 현재 saga 상태이며, downstream 지연/timeout이 있으면 `PROCESSING`, `FAILED_RETRYING`, `MANUAL_REVIEW_REQUIRED` 등으로 표현한다.
- outbox_event는 saga 상태 변화 이후 후속 처리 이벤트를 남기는 용도다.
- 후속 처리 예시는 정산, 알림, analytics, dashboard projection, replay, audit이다.
- global transaction은 없다. orchestrator는 partial state를 saga/step에 남기고, 각 downstream service의 local transaction이 자기 resource invariant를 보호한다.
- worker는 downstream service가 제공하는 방어된 command만 호출해야 하며, resource 상태를 조회한 뒤 orchestrator가 직접 판단해 나중에 차감하는 read-check-later-write 패턴을 사용하지 않는다.

### 1) Worker polling
- `checkout_saga_step`에서 실행 가능한 step을 polling
- saga별 순서 보장:
  - `CREATE_ORDER`
  - `RESERVE_STOCK`
  - `AUTHORIZE_PAYMENT`
  - `REQUEST_SHIPMENT`
- 이전 step이 `SUCCEEDED`가 아니면 다음 step 실행 금지
- worker lock 또는 optimistic status transition으로 중복 실행 방지

Worker locking strategy:
- MySQL 8에서 `SELECT ... FOR UPDATE SKIP LOCKED` 사용 가능하면 우선 사용
- 구현 단순화를 우선하면 조건부 claim update를 사용 가능:
  - `UPDATE checkout_saga_step SET status='PROCESSING', started_at=NOW(6), updated_at=NOW(6) WHERE id=? AND status='READY'`
  - affected rows가 `1`인 worker만 HTTP call 실행
- 어떤 방식을 선택하든 같은 step이 동시에 두 번 downstream call을 보내지 않는 테스트를 추가한다.
- worker는 `next_retry_at IS NULL OR next_retry_at <= NOW(6)` 조건을 지켜야 한다.

### 2) Step execution pattern
각 step은 반드시 아래 구조를 따른다.

1. Short transaction:
   - step status `PROCESSING`
   - saga status `PROCESSING`
   - saga `current_step` 업데이트
   - `started_at` 업데이트
2. No transaction:
   - downstream HTTP call
   - `Idempotency-Key: checkout:{checkoutId}:{stepName}`
   - trace/request headers propagation
   - client timeout and retry policy are explicit per downstream
3. Short transaction:
   - success: step `SUCCEEDED`, response/context 저장
   - retryable failure/timeout: step `FAILED_RETRYING`, retry_count/next_retry_at/error 저장
   - retry count exceeded: saga `MANUAL_REVIEW_REQUIRED`

Idempotency key generation rules:
- orchestrator owns `Idempotency-Key` generation
- one forward key per checkout step:
  - `checkout:{checkoutId}:CREATE_ORDER`
  - `checkout:{checkoutId}:RESERVE_STOCK`
  - `checkout:{checkoutId}:AUTHORIZE_PAYMENT`
  - `checkout:{checkoutId}:REQUEST_SHIPMENT`
- retry of the same step must reuse the exact same key
- different steps must never share a key
- the generated key must be stored on `checkout_saga_step.idempotency_key` and must match the HTTP header sent downstream

### 3) Downstream calls
- `CREATE_ORDER` -> order-service `POST /internal/orders`
- `RESERVE_STOCK` -> inventory-service `POST /internal/inventory/reserve`
- `AUTHORIZE_PAYMENT` -> payment-service `POST /internal/payments/authorize`
- `REQUEST_SHIPMENT` -> shipment-service `POST /internal/shipments`
- 모든 client timeout 명시

### 3-1) Step category and pivot policy
- `COMPENSATABLE` step 실패는 필요 시 backward recovery 대상이다.
- `PIVOT` step은 성공 후 workflow를 앞으로 밀어야 하는 경계다. pivot 이후 실패는 기본적으로 forward recovery/manual recovery 대상이다.
- `RETRIABLE` step은 성공할 때까지 재시도하거나 운영 복구해야 한다.
- MVP classification:
  - `CREATE_ORDER`: compensatable local provisional record
  - `RESERVE_STOCK`: compensatable reservation protected by inventory local transaction
  - `AUTHORIZE_PAYMENT`: compensatable authorization hold in MVP; if changed to capture/final charge, treat as pivot
  - `REQUEST_SHIPMENT`: retriable/idempotent mock in MVP; if real carrier accepts irreversible shipment request, treat as pivot/retriable with reconciliation
- Pivot급 side effect를 여러 개 연속 배치하지 않는다. 되돌릴 수 있는 reserve/check/park 성격 step은 pivot 전에 배치하고, pivot 이후에는 idempotent/retriable 상태 반영 위주로 배치한다.

### 3-2) UNKNOWN and reconciliation
- downstream timeout은 곧바로 permanent failure가 아니다.
- side effect 결과를 알 수 없으면 step status를 `UNKNOWN`으로 저장한다.
- `UNKNOWN` step은 동일 `Idempotency-Key` 조회 API 또는 downstream status API로 reconciliation한다.
- reconciliation 결과가 success면 step `SUCCEEDED`, retryable failure면 `FAILED_RETRYING`, 판단 불가/한도 초과면 `MANUAL_REVIEW_REQUIRED`로 전환한다.
- pivot step이 `UNKNOWN`이면 backward compensation을 먼저 실행하지 않고 status reconciliation을 우선한다.

### 4) Completion
- 모든 step 성공 시:
  - saga status `SUCCEEDED`
  - outbox_event `CHECKOUT_COMPLETED` 저장
  - `CHECKOUT_COMPLETED`는 후속 정산/알림/analytics/dashboard/replay consumer를 위한 event이며, checkout 성공 판정 자체는 saga DB 상태가 기준이다.

### 5) Forward recovery policy
- `FAILED_RETRYING` step은 `next_retry_at` 이후 worker가 자동 재시도할 수 있다.
- 동일 step 재시도는 동일 `Idempotency-Key`를 사용한다.
- timeout은 permanent failure가 아니라 retryable unknown outcome으로 취급한다.
- retry 이후 downstream이 이미 성공한 결과를 반환하면 step을 `SUCCEEDED`로 복구한다.
- pivot 이후 step 실패는 가능한 한 forward recovery로 처리한다.
- pivot 이후 내부 상태 반영, outbox 기록, dashboard projection 같은 작업은 idempotent/retriable해야 한다.

## Non-goals
- failure mode admin API
- manual retry API
- cancel/compensation flow
- Admin UI

## Test / Validation
- 정상 checkout이 `SUCCEEDED`까지 진행
- 각 step의 idempotency key가 downstream으로 전달됨
- 각 step별 `Idempotency-Key`가 서로 다름
- `checkout_saga_step.idempotency_key`와 실제 downstream HTTP header 값이 일치함
- 같은 step retry는 최초 실행과 동일한 `Idempotency-Key`를 재사용함
- timeout 후 retry에서 downstream 기존 성공 응답을 replay하면 step이 `SUCCEEDED`로 복구됨
- timeout/unknown outcome은 `UNKNOWN`으로 저장되고 reconciliation 후 다음 상태로 전환됨
- pivot step `UNKNOWN`은 compensation보다 reconciliation이 먼저 실행됨
- pivot 이후 실패는 backward compensation이 아니라 forward retry/manual recovery로 처리됨
- 같은 user의 서로 다른 checkout이 동시에 실행되어도 inventory/payment local transaction이 oversell/overspend를 막는 통합 테스트 추가
- HTTP call이 transaction 안에서 실행되지 않는 구조를 단위 테스트 또는 code structure로 검증
- worker locking으로 같은 READY step이 중복 실행되지 않음
- `next_retry_at` 이전 step은 실행되지 않음
- timeout/5xx 시 step `FAILED_RETRYING`
- retry count 초과 시 `MANUAL_REVIEW_REQUIRED`
- `CHECKOUT_COMPLETED` outbox event 저장
- `./scripts/test.sh`

## DoD
- checkout saga가 worker로 끝까지 실행됨
- 각 step 상태와 response/context payload가 추적 가능함
- partial failure 상태가 saga/step에 남음
- partial state와 pivot/UNKNOWN 상태가 운영자가 추적 가능한 형태로 남음
- checkout step 실행이 Kafka/outbox command delivery에 의존하지 않음
- distributed transaction 없이 최종 일관성을 유지하는 구조가 코드에 드러남
- resource invariant는 owning service local transaction이 방어하고 orchestrator는 이를 우회하지 않음

## Codex Prompt
Implement Commerce MSA phase 4:
- Add checkout-orchestrator DB polling worker.
- Execute CREATE_ORDER, RESERVE_STOCK, AUTHORIZE_PAYMENT, REQUEST_SHIPMENT in order.
- Use short transaction -> HTTP call outside transaction -> short transaction.
- Use HTTP orchestration for the core checkout flow; do not advance steps through Kafka/outbox commands.
- Implement step category handling, pivot-aware recovery, UNKNOWN status, and reconciliation before compensation.
- Add worker locking via SKIP LOCKED or conditional claim update, with a duplicate execution test.
- Pass `Idempotency-Key` and trace/request headers to every downstream service.
- Test that generated idempotency keys are unique per step, persisted on saga_step, and reused on retry.
- Test concurrent workflows prove downstream local transactions prevent oversell/overspend.
- Mark retryable failures as FAILED_RETRYING and complete saga with CHECKOUT_COMPLETED follow-up outbox event when all steps succeed.
