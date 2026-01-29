# B-0225 — BFF(Search API) Introduction (Spring Boot) — v1 Range: /search /autocomplete /books/:id

## Goal
{"PageInfo":{"component":"PageInfo"},"Hero":{"component":"Hero","subTitle":"","title":""},"ImageMapWithCityLink":{"component":"ImageMapWithCityLink"}}
BFF Forces “External Request Standards”: **request id/trace id issuance, fan-out, response assembly, error standardization, event history**.

> v1 Range:   TBD  ,   TBD  ,   TBD  
>  TBD  MIROOM WITH Sprint 5(add).

## Why
- Certification/Laterime/Observation/Contract/Error standardization if scattered by the service, the operation is broken.
- If the front calls internal service (QS/SR/AC) directly, it is difficult to change/disable/security control.
- In BFF, you need to control the “Policy” and can be degrade safe.

## In Scope
### 1) External API (BFF provided)
- `GET /health` (liveness)
- `GET /ready` (readiness: downstream connectivity check)
- `POST /search`
- `GET /autocomplete?q=...`
- `GET /books/{docId}`

New *Features of request/ response (operation type)* News
-  TBD   included in all responses
- Error Unified by Common Error Sema (e.g.   TBD ,   TBD  ,   TBD  )
-  TBD  (OTel) Pass/Power

### 2) Internal fan-out (BFF calls)
- New  TBD   Flow:
  - BFF → QS(  TBD  ) → SR( TBD  ) → RS/MIS inside SR
- New  TBD   Flow:
  - BFF → AC(`/internal/autocomplete`)
- New  TBD   Flow:
  - BFF → (G Zone Book detail endpoint: B-0212 Gender or DB direct inquiry service)

### 3) Request/Trace ID issue rules
- inbound   TBD  Not created(UUIDv7 recommended)
- New  TBD   ,   TBD     Passed to QS/SR/AC
- Always on log   TBD  include

### 4 days ago ) Outbox Records (Events “Records Only”, Transfers B-0248)
- The v1 range doesn’t force “transport”, but only the “outbox record interface**.
- Example:   TBD  ,   TBD  ,   TBD  loading events like outbox(optional)
  - CROSS   TBD   Actual Relay at Ticket(B-0248)

### 5) Degrade/Fallback(min)
- downstream timeout:
  - New  TBD  : "No error"** Minimum result/bin results** +   TBD   
  - New  TBD  : Instantly returns frequent results (latest budgets)
- Direct-call fallback is available in the front (U/A).

## Out of Scope
- New  TBD   (Sprint 5)
- AuthN /AuthZ + Rate limit (From B-0227)
- Outbox → Kafka Relay(B-0248)

## Deliverables
- New News Spring Boot BFF Project Scanning (ports/health/ready)
- [ ]   TBD   ,   TBD  ,   TBD  routing + response assembly
- [ ] request_id/trace propagation
- [ ] Common error schema + exception map
- [ ] outbox recording interface (Minimum DB table/DAO)

## DoD
- When Web(User/Admin) is attached to BFF, three endpoints are normal operation
- QS/SR/AC failure/timeout response BFF to “standard error/standard degrade”
- request id/trace id returns to end-to-end

## Suggested Files
- `bsl-bff/` (new)
- `bsl-bff/src/main/java/.../controller/*`
- `bsl-bff/src/main/java/.../clients/{QsClient,SrClient,AcClient}`
- `bsl-bff/src/main/java/.../common/{ErrorResponse,RequestIdFilter,TraceConfig}`
- `./db/migration/V12__insert_catalog_data.sql` (outbox)

## Codex Prompt
Build **B-0225**:
- Create Spring Boot BFF with endpoints: POST /search, GET /autocomplete, GET /books/{docId}
- Implement downstream HTTP clients to QS/SR/AC with timeouts and propagated headers (x-request-id, traceparent)
- Standardize error responses and include request_id in all responses
- Add minimal outbox persistence interface (table + repository) for future Kafka relay
- Provide docker-compose/local env wiring with fixed ports
