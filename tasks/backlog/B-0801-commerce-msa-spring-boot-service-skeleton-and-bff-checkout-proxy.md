# B-0801 — Commerce MSA Service Skeleton + BFF Checkout Proxy

## Priority
- P0

## Dependencies
- B-0800
- Existing Commerce Service baseline
- Existing BFF routing/auth/session/header propagation

## Goal
Commerce modular monolith의 core write path를 MSA 실험 구조로 분리하기 위한 첫 단계로 checkout/order/payment/inventory/shipment/refund 서비스 골격을 만든다.

이 단계의 목표는 DB나 saga worker 구현이 아니라, 각 서비스가 독립 Spring Boot 모듈로 컴파일되고 로컬에서 개별 포트로 뜨며 BFF가 checkout write entrypoint를 checkout-orchestrator-service로 위임할 수 있게 만드는 것이다.

이번 MSA 범위는 checkout/order/payment/inventory/shipment/refund까지만 포함한다. cart/catalog/settlement/customer/merchandising/support는 legacy `commerce-service`에 남긴다.

## Scope
### 1) New Spring Boot modules
- `services/checkout-orchestrator-service` 포트 `8091`
- `services/order-service` 포트 `8092`
- `services/payment-service` 포트 `8093`
- `services/inventory-service` 포트 `8094`
- `services/shipment-service` 포트 `8097`
- `services/refund-service` 포트 `8098`
- `settings.gradle`에 신규 모듈 등록
- 기존 검색 계열 서비스(QS/Search/AC/Ranking/MIS/LLMGW)는 변경하지 않음

### 2) Minimal APIs
- 각 서비스 `GET /health`
- checkout-orchestrator:
  - `POST /internal/checkouts` dummy response
  - `GET /internal/checkouts/{checkoutId}` dummy response
  - `POST /internal/checkouts/{checkoutId}/steps/{stepName}/retry` dummy response
  - `POST /internal/checkouts/{checkoutId}/cancel` dummy response

### 3) BFF checkout proxy
- BFF public API 추가:
  - `POST /v1/checkout`
  - `GET /v1/checkout/{checkoutId}`
  - `POST /v1/checkout/{checkoutId}/steps/{stepName}/retry`
  - `POST /v1/checkout/{checkoutId}/cancel`
- BFF는 위 요청을 checkout-orchestrator-service internal API로 위임
- core checkout flow는 HTTP orchestration으로 즉시 가능한 결과를 반환한다.
- BFF 응답은 Kafka/outbox consumer 완료를 기다리지 않는다.
- `x-trace-id`, `x-request-id`, `traceparent`, `x-user-id`, `x-session-id`, `Idempotency-Key` 전달 구조를 남김
- 외부 클라이언트가 하위 서비스를 직접 호출하지 않는 구조 유지

### 4) API shape contract draft
`POST /v1/checkout` request는 1차에서 아래 shape로 고정한다.

```json
{
  "checkout_key": "user:101:cart:abc:attempt:1",
  "user_id": "101",
  "items": [
    {
      "book_id": "book-001",
      "title": "string",
      "quantity": 1,
      "unit_price": 12900
    }
  ],
  "payment": {
    "method": "MOCK_CARD",
    "amount": 12900,
    "currency": "KRW"
  },
  "shipping_address": {
    "recipient": "string",
    "phone": "string",
    "zip": "string",
    "address1": "string",
    "address2": "string"
  }
}
```

`POST /v1/checkout` response는 아래 최소 shape를 반환한다.

```json
{
  "checkout_id": 1,
  "checkout_key": "user:101:cart:abc:attempt:1",
  "status": "PENDING",
  "current_step": null,
  "steps": [
    { "step_name": "CREATE_ORDER", "status": "READY" }
  ]
}
```

### 5) Migration switch
- 기존 Commerce API를 한 번에 제거하지 않고 BFF 설정으로 전환 가능하게 둔다.
- `BFF_CHECKOUT_BACKEND=orchestrator|legacy` 같은 flag를 두고 기본값은 티켓 구현 시 명시한다.
- 신규 `/v1/checkout`만 orchestrator로 보내고, 기존 cart/order/refund API는 이 단계에서 유지한다.

## Non-goals
- DB schema/migration 구현
- saga worker 구현
- 하위 서비스 실제 domain write 구현
- failure mode 구현
- 기존 Commerce Service 삭제

## Test / Validation
- `./gradlew :services:checkout-orchestrator-service:test`
- `./gradlew :services:order-service:test`
- `./gradlew :services:payment-service:test`
- `./gradlew :services:inventory-service:test`
- `./gradlew :services:shipment-service:test`
- `./gradlew :services:refund-service:test`
- BFF checkout proxy controller/client unit test
- `./scripts/test.sh`

## DoD
- 신규 6개 서비스가 독립 모듈로 컴파일됨
- 각 서비스가 지정 포트 설정을 가짐
- BFF `/v1/checkout*` API가 checkout-orchestrator로 프록시됨
- BFF checkout proxy가 HTTP orchestration entrypoint임이 코드/설정/문서에 드러남
- checkout request/response 최소 shape가 코드와 테스트에 반영됨
- checkout backend 전환 flag가 존재함
- HTTP client timeout 설정이 존재함
- 검색/RAG/Autocomplete/Ranking 계열 변경 없음

## Codex Prompt
Implement only Commerce MSA phase 1:
- Add Spring Boot skeleton modules for checkout-orchestrator, order, payment, inventory, shipment, and refund.
- Configure ports 8091, 8092, 8093, 8094, 8097, and 8098.
- Add health and dummy internal endpoints.
- Add BFF `/v1/checkout` proxy endpoints to checkout-orchestrator.
- Use the fixed checkout request/response shape from this ticket.
- Ensure the checkout proxy returns the immediate available orchestrator result and does not depend on Kafka/outbox.
- Add a BFF checkout backend feature flag so legacy Commerce can coexist during migration.
- Do not add saga worker or DB migrations yet.
