# B-0806 — Commerce MSA Scenario Tests + Documentation

## Priority
- P1

## Dependencies
- B-0800
- B-0801
- B-0802
- B-0803
- B-0804
- B-0805

## Goal
Commerce MSA checkout core 구조를 회귀 테스트와 문서로 고정한다.

이 티켓은 checkout/order/payment/inventory/shipment/refund core 구현 완료 후 "왜 이렇게 나눴는지", "어떻게 실행하는지", "어떤 실패를 실험할 수 있는지"를 저장소 문서와 테스트로 남긴다. 전체 Commerce API map에서는 cart/catalog/settlement/customer/merchandising/support를 legacy-kept로 명시한다.

## Scope
### 1) Scenario tests
최소 시나리오:
- checkout 정상 성공
- payment `FAIL_500` -> checkout retryable failure
- payment `SUCCESS_BUT_TIMEOUT` -> retry 시 idempotency로 중복 결제 없이 성공 복구
- inventory 재고 부족 -> payment cancel compensation 발생
- shipment `TIMEOUT` -> `REQUEST_SHIPMENT` step `FAILED_RETRYING`
- manual retry API 호출 시 실패 step만 다시 실행
- 같은 `checkout_key` 중복 요청 시 같은 checkout 반환
- 같은 `Idempotency-Key`로 payment authorize 중복 호출 시 같은 payment 반환
- refund 요청/승인/처리 정상 흐름
- refund 처리 중 payment cancel 실패 시 retryable 상태 유지
- 같은 `Idempotency-Key`로 refund process 중복 호출 시 중복 결제취소/재고복원 없음

Idempotency/key propagation assertions:
- checkout-orchestrator generates one distinct forward `Idempotency-Key` per step
- downstream mock/server captures prove each HTTP call received the expected key
- persisted `checkout_saga_step.idempotency_key` equals the downstream HTTP header
- automatic retry and manual retry reuse the original step key
- compensation uses separate `checkout:{checkoutId}:{stepName}:compensate` keys
- duplicate checkout/order/payment/inventory/shipment/refund calls assert row counts, not only response status
- `SUCCESS_BUT_TIMEOUT` scenarios assert there is exactly one payment authorization, one stock reservation, or one shipment request

Consistency/recovery assertions:
- no test assumes global transaction or distributed rollback
- same user concurrent checkout requests do not overspend/oversell because payment/inventory owning services enforce local transactions
- inventory concurrent reserve test proves stock never goes negative
- payment duplicate/concurrent authorize test proves duplicate PG authorization is not created for the same idempotency key
- timeout produces `UNKNOWN` before reconciliation when side effect outcome is unclear
- reconciliation can move `UNKNOWN` to `SUCCEEDED`, `FAILED_RETRYING`, or `MANUAL_REVIEW_REQUIRED`
- pivot-success followed by downstream failure uses forward retry/manual review, not automatic rollback
- pivot reversal/compensation requires explicit operator reason/approval context

### 2) Documentation
- `docs/ARCHITECTURE.md`
  - Commerce modular monolith 설명을 Checkout Orchestrator 기반 MSA로 갱신
  - core checkout write path는 HTTP orchestration + Saga + Idempotency + Retry + Manual Recovery라고 명시
  - Kafka/outbox는 core checkout command path가 아니라 정산, 알림, analytics, dashboard, replay 같은 후속 처리용이라고 명시
  - Forward Recovery와 Backward Recovery를 모두 지원한다고 명시
- `docs/TECHNICAL_GUIDE.md`
  - 서비스 맵, 포트, checkout flow 갱신
- 신규 문서:
  - `docs/COMMERCE_MSA_SAGA.md`
- Core Commerce route ownership:
  - `docs/COMMERCE_MSA_API_MAP.md`와 링크하고 MSA 범위(checkout/order/payment/inventory/shipment/refund)와 legacy 유지 범위를 명확히 구분

### 3) COMMERCE_MSA_SAGA.md content
- 목적
- 서비스 구성
- checkout saga flow
- core checkout HTTP orchestration model
- DB schema 요약
- transaction boundary
- global transaction이 없는 이유와 local transaction 방어 전략
- service-owned invariant matrix
- step category: `COMPENSATABLE`, `PIVOT`, `RETRIABLE`
- pivot transaction 기준과 workflow ordering rule
- `UNKNOWN` 상태와 reconciliation 절차
- 실패/재시도 정책
- Forward Recovery vs Backward Recovery 기준
- 상태 전이표
- Idempotency-Key 규칙
- worker locking 전략
- outbox event catalog
- failure mode 실험 방법
- 운영자 상태 조회/수동 재처리 방법

### 4) Outbox event catalog
Outbox event는 checkout/refund core flow를 진행시키는 command가 아니다. 아래 이벤트는 후속 처리 consumer를 위한 domain event catalog다.

Primary follow-up use cases:
- settlement/정산
- notification/알림
- analytics
- dashboard projection
- replay
- audit/recovery inspection

최소 이벤트:
- `CHECKOUT_STARTED`
- `CHECKOUT_STEP_FAILED`
- `CHECKOUT_MANUAL_REVIEW_REQUIRED`
- `CHECKOUT_COMPLETED`
- `CHECKOUT_CANCELLING`
- `CHECKOUT_CANCELLED`
- `CHECKOUT_CANCEL_FAILED`
- `REFUND_REQUESTED`
- `REFUND_APPROVED`
- `REFUND_COMPLETED`
- `REFUND_FAILED`

각 event payload는 최소 아래 필드를 포함한다.
- `event_version`
- `checkout_id`
- `checkout_key`
- `user_id`
- `status`
- `current_step`
- `failed_step` 또는 `null`
- `reason_code` 또는 `null`
- `trace_id`
- `request_id`
- `occurred_at`

## Non-goals
- 새 기능 구현
- 검색 계열 문서 대규모 개편
- Kafka 전환
- Kafka/outbox 기반 checkout command orchestration

## Test / Validation
- Commerce MSA scenario tests pass
- `./scripts/test.sh`
- idempotency tests include response replay and database row-count assertions
- retry/compensation tests assert exact `Idempotency-Key` values
- 문서의 포트가 `application.yml`과 일치
- 문서의 상태 전이표가 코드 enum/transition guard와 일치
- 문서의 step category/recovery policy가 코드 상수와 일치
- concurrent checkout/resource contention tests pass
- UNKNOWN/reconciliation tests pass
- pivot-aware recovery tests pass
- outbox event catalog가 코드 상수와 일치
- 문서가 core checkout flow를 HTTP orchestration으로 설명하고, Kafka/outbox를 후속 처리로만 설명함
- API surface와 contracts가 충돌하지 않음

## DoD
- Commerce MSA 핵심 실패 시나리오가 자동화됨
- 신규 서비스/포트/흐름이 문서화됨
- 새 개발자가 `docs/COMMERCE_MSA_SAGA.md`만 보고 로컬 실험을 시작할 수 있음

## Codex Prompt
Implement Commerce MSA phase 6:
- Add scenario tests for normal checkout, failure modes, idempotent retry, duplicate checkout_key, compensation, and refund processing.
- Update architecture and technical guide docs for Commerce MSA.
- Add `docs/COMMERCE_MSA_SAGA.md` with HTTP orchestration flow, schemas, transaction boundaries, forward/backward recovery, state transitions, idempotency, worker locking, follow-up outbox events, and operator recovery guide.
- Include global-vs-local transaction rationale, local invariant ownership, pivot transaction rules, UNKNOWN/reconciliation, and side-effect safety tests.
- Document that Kafka/outbox is reserved for settlement, notification, analytics, dashboard, replay, and audit follow-up processing.
