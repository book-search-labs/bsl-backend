# B-0225 — BFF(Search API) 도입 (Spring Boot) — v1 범위: /search /autocomplete /books/:id

## Goal
현재 프론트(U/A)가 **Query Service(QS)를 direct-call** 하고 있는 구조를, 운영형 표준인 **BFF 단일 진입점**으로 옮긴다.  
BFF는 “외부 요청의 표준”을 강제한다: **request_id/trace_id 발급, fan-out, 응답 조립, 에러 표준화, 이벤트(outbox) 기록**.

> v1 범위: `/search`, `/autocomplete`, `/books/:id`  
> `/chat`은 Sprint 5(추후)로 미룸.

## Why
- 인증/레이트리밋/관측/계약/에러 표준화를 서비스별로 흩뿌리면 운영이 망가진다.
- 프론트가 내부 서비스(QS/SR/AC)를 직접 호출하면 변경/장애/보안 통제가 어렵다.
- BFF에서 “정책”을 통제해야 무중단 마이그레이션과 안전한 degrade가 가능하다.

## In Scope
### 1) External API (BFF가 제공)
- `GET /health` (liveness)
- `GET /ready` (readiness: downstream connectivity check)
- `POST /search`
- `GET /autocomplete?q=...`
- `GET /books/{docId}`

**요청/응답 특징(운영형)**
- 모든 응답에 `request_id` 포함
- 에러는 공통 에러 스키마(예: `error.code`, `error.message`, `error.details`)로 통일
- `traceparent`(OTel) 전달/전파

### 2) Internal fan-out (BFF가 호출)
- `/search` 플로우(기본):
  - BFF → QS(`/query/prepare`) → SR(`/internal/search`) → (필요 시) RS/MIS는 SR 내부에서
- `/autocomplete` 플로우:
  - BFF → AC(`/internal/autocomplete`)
- `/books/:id` 플로우:
  - BFF → (기존 Book detail endpoint: B-0212 경유 or DB 직접 조회 서비스)

### 3) Request/Trace ID 발급 규칙
- inbound에 `x-request-id` 없으면 생성(UUIDv7 권장)
- `x-request-id`, `traceparent`를 QS/SR/AC로 그대로 전달
- 로그에 항상 `{request_id, trace_id, path, latency_ms, status}` 포함

### 4) Outbox 기록(이벤트는 “기록까지만”, 전송은 B-0248)
- v1 범위에서는 “전송”까지 강제하지 않고, **outbox 기록 인터페이스**만 깔아둔다.
- 예: `search_request`, `autocomplete_request`, `book_view` 같은 이벤트를 outbox에 적재(옵션)
  - 추후 `Outbox → Kafka` 티켓(B-0248)에서 실제 릴레이

### 5) Degrade/Fallback(최소)
- downstream timeout 시:
  - `/search`: “에러”가 아니라 **최소 결과/빈 결과** + `degraded=true`를 선택 가능(정책)
  - `/autocomplete`: 즉시 빈 결과 반환(지연 예산 최우선)
- (중요) direct-call fallback은 **프론트(U/A)에서** 토글로 구현(U-0130/A-0120)

## Out of Scope
- `/chat` (Sprint 5로)
- AuthN/AuthZ + Rate limit (B-0227에서)
- Outbox → Kafka 릴레이(B-0248에서)

## Deliverables
- [ ] Spring Boot BFF 프로젝트 스캐폴딩(ports/health/ready)
- [ ] `/search`, `/autocomplete`, `/books/:id` 라우팅 + 응답 조립
- [ ] request_id/trace propagation
- [ ] 공통 에러 스키마 + 예외 매핑
- [ ] outbox 기록 인터페이스(최소 DB 테이블/DAO)

## DoD
- 로컬에서 Web(User/Admin)이 BFF로 붙었을 때 3개 엔드포인트가 정상 동작
- QS/SR/AC 장애/타임아웃 시에도 BFF가 “표준 에러/표준 degrade”로 응답
- 로그에 request_id/trace_id가 end-to-end로 이어짐

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
