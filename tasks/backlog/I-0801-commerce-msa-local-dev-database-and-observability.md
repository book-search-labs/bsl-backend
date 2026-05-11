# I-0801 — Commerce MSA Local Dev Database + Observability

## Priority
- P1

## Dependencies
- B-0800
- B-0801
- B-0802
- B-0803

## Goal
Commerce MSA 실험을 로컬에서 안정적으로 실행할 수 있도록 서비스별 DB/schema, compose 설정, 관측성 기본값을 정리한다.

## Scope
### 1) Service database separation
가능하면 MySQL 안에 서비스별 database/schema를 분리한다.

- `checkout_orchestrator_db`
- `order_db`
- `payment_db`
- `inventory_db`
- `shipment_db`
- `refund_db`

각 서비스는 자기 DB만 바라보도록 `application.yml`과 환경변수를 분리한다.

### 2) Local compose/dev scripts
- 신규 서비스 포트 노출:
  - checkout-orchestrator `8091`
  - order `8092`
  - payment `8093`
  - inventory `8094`
  - shipment `8097`
  - refund `8098`
- 기존 `pg-simulator`와 `8092` 충돌 정리
- 로컬 실행 순서 문서화
- 필요 시 seed script 추가:
  - inventory `book_stock` sample rows
  - checkout happy-path sample payload

### 3) Legacy coexistence and migration
- 기존 `commerce-service`는 이 인프라 티켓에서 삭제하지 않는다.
- BFF checkout backend flag로 신규 checkout-orchestrator와 legacy commerce checkout 경로를 전환할 수 있게 한다.
- 전환 범위는 checkout/order/payment/inventory/shipment/refund API만 신규 MSA로 보낸다.
- 기존 cart/catalog/settlement/customer/merchandising/support API는 legacy `commerce-service`에 남긴다.
- core checkout flow는 HTTP orchestration으로 동작하며 Kafka/outbox relay 없이도 로컬에서 정상 실험 가능해야 한다.
- 포트 충돌 정책:
  - 신규 order-service가 `8092`를 사용한다.
  - 기존 `pg-simulator`는 다른 포트로 이동하거나 profile off 기본값을 문서화한다.

### 4) Observability baseline
- `x-trace-id`, `x-request-id`, `traceparent` propagation 확인
- actuator prometheus endpoint 노출
- checkout saga metrics 기본 정의:
  - `checkout_saga_started_total`
  - `checkout_saga_completed_total`
  - `checkout_saga_failed_total{step,reason}`
  - `checkout_saga_unknown_total{step,reason}`
  - `checkout_saga_reconciliation_total{step,result}`
  - `checkout_saga_pivot_manual_review_total{step,reason}`
  - `checkout_saga_manual_review_total`
  - `checkout_compensation_total{step,result}`
  - `commerce_resource_contention_total{service,resource,result}`

## Non-goals
- Kubernetes production deployment
- Kafka/Outbox Relay 전환
- Kafka/outbox 기반 checkout command orchestration
- full Grafana dashboard

Kafka/outbox relay를 나중에 추가하더라도 목적은 정산, 알림, analytics, dashboard projection, replay, audit 같은 후속 처리다. checkout/order/payment/inventory/shipment/refund core write path의 성공/실패 판정은 각 서비스 DB 상태와 HTTP orchestration 결과를 기준으로 한다.

로컬 실험 환경은 global transaction이 없는 상태에서 partial state, UNKNOWN, reconciliation, local resource contention을 재현할 수 있어야 한다.

## Test / Validation
- `docker compose` 또는 로컬 dev script로 required data services 기동
- 신규 6개 서비스 health check 성공
- 각 서비스 DB migration 적용
- trace/request header가 BFF -> orchestrator -> downstream으로 전달됨
- concurrent checkout/resource contention smoke test가 inventory/payment local transaction 방어를 검증
- UNKNOWN/reconciliation smoke test가 metric/log에 남음
- `./scripts/test.sh`

## DoD
- 로컬에서 Commerce MSA 서비스들을 같은 포트 계약으로 실행 가능
- 서비스별 DB 경계가 설정으로 분리됨
- pg-simulator 포트 충돌이 해소됨
- legacy commerce와 신규 core Commerce MSA의 공존/전환 방법이 문서화됨
- Kafka/outbox relay 없이 core checkout HTTP orchestration을 실행할 수 있음
- local dev에서 partial failure, UNKNOWN, reconciliation, resource contention을 관측 가능
- 최소 관측 지표와 header propagation이 확인됨

## Codex Prompt
Implement Commerce MSA local dev infrastructure:
- Add per-service MySQL database/schema configuration.
- Update compose/dev scripts for checkout-orchestrator, order, payment, inventory, shipment, and refund ports.
- Resolve pg-simulator port conflict.
- Document legacy Commerce coexistence and BFF core Commerce route switching.
- Ensure local checkout works through HTTP orchestration without Kafka/Outbox Relay.
- Add observability for UNKNOWN, reconciliation, pivot manual review, and resource contention.
- Add basic metrics and trace/request header propagation checks.
- Do not migrate to Kafka yet.
