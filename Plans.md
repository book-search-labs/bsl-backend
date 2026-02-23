# Plans.md — Book Search Labs (BSL) Final v3 (End-to-End Roadmap)

> Goal: **“Data pipeline → Search/Recommendations → Commerce → RAG chatbot → Ops/Observability/Release”**  
> An execution plan (ticket roadmap) to reach a level that is actually launchable/operable

---

## 0) Scope / Principles

### Scope (Included)
- **U(Web User), A(Web Admin), B(Backend/Services), I(Infra/Platform)** all included
- Front-end includes **zero-downtime migration** from **QS direct-call → via BFF**
- Includes **QS/SR hardening (cost/latency/stability/debugging/experiments)**
- Includes **MIS (Model Inference Service)** introduction
- Includes **Kafka integration (shared ops loop for Autocomplete/Ranking)**
- Includes **LTR pipeline + offline eval regression tests (deployment gate)**
- Includes **RAG-based chatbot (product-grade: citations/reproducibility/feedback loop)**
- Includes **Commerce (orders/payments/shipping/refunds)**
- Includes **Observability / Security / Release**

### Principles (Production-grade)
- All external/front traffic ultimately controlled via a **single BFF entrypoint**
- Events consistently via **Outbox → Kafka** (idempotent / replay-safe)
- Models **isolated in MIS**, SR/RS ship with **degrade/fallback** by default
- Quality blocked in CI by **offline eval regression gates** (“no shipping performance regressions”)
- OpenSearch operational standard fixed to **alias + blue/green reindex**

---

## 1) Fixed Prefix / Ports

### Ticket Prefix
- **B-xxxx**: Backend(services/domains/data/indexing/models)
- **U-xxxx**: User Web(UI/UX)
- **A-xxxx**: Admin Web(UI/OPS)
- **I-xxxx**: Infra/Platform(deploy/observability/security/ops)

### Fixed Ports (current agreement)
- web-admin: **5173**
- web-user: **5174**
- search-service: **8080**
- autocomplete-service: **8081**
- query-service: **8001**

---

## 2) Current DONE (baseline)

### ✅ Completed tickets (ordered from tasks/done)

- ✅ **A-0106** — Admin Autocomplete Ops Screen (boost/ban/trends/CTR)
- ✅ **A-0109** — Product Ops UI (Seller/Offer/Inventory)
- ✅ **A-0110** — Payment & Refund Ops UI
- ✅ **A-0111** — Shipping Ops UI (labels/status/issues)
- ✅ **A-0113** — Ops: Reindex / Job Run UI (job_run/reindex_job/ops_task)
- ✅ **A-0120** — Web Admin: API 호출을 BFF로 전환(무중단)
- ✅ **A-0122** — Admin Doc/Index Ops UI (upload/reindex/version/rollback)
- ✅ **A-0123** — Admin RAG Eval & Labeling UI (question sets, judgments)
- ✅ **A-0124** — Admin Failure Case + Rerank Debug + Replay UI (Search/RAG)
- ✅ **A-0125** — Admin Model Registry & Metrics Report UI (rollout/rollback)
- ✅ **A-0130** — Admin Authority/Merge Ops UI (material merge, agent alias)
- ✅ **A-0131** — Admin Index Ops UI (Indices Overview)
- ✅ **A-0132** — Admin Index Ops UI (Doc Lookup)
- ✅ **A-0133** — Admin Search Compare UI (A/B/C)
- ✅ **A-0134** — Admin Dashboard Live Metrics
- ✅ **A-0135** — Admin Settings Persistence
- ✅ **A-0110** — Admin Web: 검색 Debug/Enhance 관측 + KDC 트리 뷰어
- ✅ **B-0212** — Search Service: Book Detail API (by docId)
- ✅ **B-0213** — Autocomplete Service: API v1 (OpenSearch-backed)
- ✅ **B-0214** — Autocomplete Service: OpenSearch-backed suggestions (ac_suggest_read)
- ✅ **B-0220** — Ingest NLK LOD JSON(-LD) datasets into MySQL + OpenSearch (streaming, local-first)
- ✅ **B-0221a Canonical → OpenSearch Reindex (local-first, aggressive)**
- ✅ **B-0221b** — Authority/Merge v1 (material/agent dedup minimal set)
- ✅ **B-0222** — Canonical ETL Idempotent Incremental Upsert (payload_hash)
- ✅ **B-0223** — Index Writer Service (reindex_job state machine, pause/resume)
- ✅ **B-0223a** — Reindex Safety Guards (throttle/backoff/retry/partial failure)
- ✅ **B-0224** — Synonym/Normalization Deployment Pipeline (versioning + rollback)
- ✅ **B-0225** — BFF(Search API) 도입 (Spring Boot) — v1 범위: /search /autocomplete /books/:id
- ✅ **B-0226** — Contract Freeze (OpenAPI/JSON Schema) + CI Compatibility Gate
- ✅ **B-0227** — AuthN/AuthZ (User/Admin) + Rate Limit + Admin RBAC
- ✅ **B-0228** — Autocomplete Index/Alias Strategy (ac_candidates_v*, ac_read/ac_write)
- ✅ **B-0229** — Redis Hot Prefix Cache for Autocomplete (TopK, TTL/size policy)
- ✅ **B-0230** — Emit Autocomplete Events (ac_impression / ac_select) via Outbox → Kafka
- ✅ **B-0231** — Autocomplete Aggregation Consumer (CTR/Popularity → OpenSearch/Redis)
- ✅ **B-0232** — Emit Search Events (search_impression / click / dwell) for Ranking/LTR Loop
- ✅ **B-0237** — Catalog Commerce APIs: SKU / Offer / current_offer
- ✅ **B-0238** — Inventory: balance/ledger + transaction rules (reserve/release/deduct/restock)
- ✅ **B-0239** — Cart API (cart/cart_item) + concurrency & price snapshot
- ✅ **B-0240** — Order 생성 + 상태머신 + order_event (Saga-ready)
- ✅ **B-0241** — Payment 연동 (Mock PG → Real PG 확장 설계) + idempotency + retry/webhook
- ✅ **B-0242** — Shipment/Tracking (shipment/shipment_item/shipment_event) + carrier status updates
- ✅ **B-0243** — Refund/부분환불 + 재고복원(ledger) 플로우 (Idempotent)
- ✅ **B-0248** — Outbox → Kafka Relay (Idempotent, Retry-safe)
- ✅ **B-0250** — Feature Fetch Layer (Online KV) v1: ctr/popularity/freshness
- ✅ **B-0251** — Feature Spec Single Source: features.yaml (Online/Offline parity)
- ✅ **B-0252** — Ranking Service Debug Mode (Explain + Replay-ready)
- ✅ **B-0253** — Ranking Cost Guardrails (TopN/TopK budgets + Conditional Rerank)
- ✅ **B-0260** — QueryContext v1 Contract + Trace Propagation (E2E)
- ✅ **B-0261** — QS Normalize/Detect 강화 (NFKC/ICU + 초성/권차/ISBN/시리즈 + canonicalKey)
- ✅ **B-0262** — QS 2-pass Gating (cost governor) for spell/rewrite/RAG
- ✅ **B-0263** — QS Rewrite Quality Loop (before/after logging + failure curation)
- ✅ **B-0264** — QS Query Cache (normalize cache + enhance cache) for cost reduction
- ✅ **B-0264a-qsv1-prepare-canonical-key-bugfix**
- ✅ **B-0264b-qsv1-rewrite-failures-endpoint-bugfix**
- ✅ **B-0265-qsv1-2pass-spell-t5-implementation**
- ✅ **B-0265a-qsv1-spell-gating-acceptance**
- ✅ **B-0266-qsv1-2pass-rewrite-llm-implementation**
- ✅ **B-0266** — Search Service Retrieval Strategy (BM25 + Vector + Fusion/RRF) 플러그인화
- ✅ **B-0266a** — Query Embedding 생성 경로 확정 (OS 모델 vs Inference 경로)
- ✅ **B-0266a-qsv1-rewrite-acceptance-abtest-logic**
- ✅ **B-0267** — SR Reliability: Circuit Breaker / Timeout / Hedged + Degraded Response(0건 방지)
- ✅ **B-0267-qsv1-rag-rewrite-implementation**
- ✅ **B-0267a-qsv1-enhance-contracts-examples**
- ✅ **B-0268** — SR Debug/Explain API + Playground Snapshot (Score breakdown)
- ✅ **B-0268-qsv1-e2e-tests-prepare-enhance-cache-budgets**
- ✅ **B-0269** — SR Cache Layer: SERP 캐시 + Book Detail 캐시(ETag/Cache-Control)로 p99 방어
- ✅ **B-0270** — MIS 골격: Stateless Inference API(Ready/Models/Score) + Concurrency/Queue/Timeout
- ✅ **B-0271** — MIS: Reranker ONNX Runtime 서빙(v1) + (옵션) Dynamic Batching
- ✅ **B-0272** — RS(orchestrator) ↔ MIS 계약 고정 + 부하테스트(배치/latency) + Canary-ready
- ✅ **B-0273** — SR/RS Fallback 정책(운영 안전): MIS 장애/지연 시 Degrade로 SLA 유지
- ✅ **B-0274** — Model Registry 연동: Active 버전 라우팅 + Canary Rollout/Rollback
- ✅ **B-0280** — RAG Ingest: 문서 수집/정규화/청킹 + 변경 감지 + 증분 업데이트
- ✅ **B-0281** — OpenSearch RAG Index 설계: docs_doc_v* + docs_vec_v* (highlight/citations 키 고정)
- ✅ **B-0282** — QS `/chat` 오케스트레이션: Rewrite → Retrieve → Rerank → Generate (citations 강제, 스트리밍)
- ✅ **B-0283** — LLM Gateway: 키/레이트리밋/리트라이/감사/비용 통제(중앙화)
- ✅ **B-0284** — Chat Feedback 이벤트 + 평가 파이프라인(👍👎/환각/근거부족) → 개선 루프
- ✅ **B-0290** — LTR 학습 라벨 생성 잡(implicit labeling): click/dwell/cart/purchase → relevance label
- ✅ **B-0291** — Position Bias 최소 대응: 탐색 트래픽/간단 IPS/인터리빙 중 1개(+가드레일)
- ✅ **B-0292** — CTR/Popularity 집계 컨슈머(시간감쇠/스무딩) → Feature Store 업데이트
- ✅ **B-0293** — Point-in-time correctness: 피처 스냅샷/타임조인(Offline/Online 일치)
- ✅ **B-0294** — LTR 학습 파이프라인(LightGBM LambdaMART v1) + 모델 아티팩트 등록
- ✅ **B-0295** — Offline Eval Runner + 회귀 게이트(배포 차단)
- ✅ **B-0300** — Material 대표 선정(판본/세트/리커버) 룰 고도화 + SERP 그룹핑
- ✅ **B-0301** — Agent authority(저자 표기 변형) 정규화 고도화 + alias 사전 운영화
- ✅ **B-0302** — Query Embedding 캐시/핫쿼리 벡터 캐시(비용 절감)
- ✅ **B-0303** — Fusion 정책 실험 프레임(RRF vs Weighted) + 실험 연결
- ✅ **B-0304** — Chunk→Doc 승격 로직 고도화(다양성/중복 제거)
- ✅ **B-0305** — 이벤트 멱등키(dedup_key) 표준화 가이드(전 event_type 공통)
- ✅ **B-0306** — Global budget governor(검색/챗/리랭킹 공통 예산제)
- ✅ **B-0307** — 사용자 데이터 export/delete (GDPR-lite, 포트폴리오 가점)
- ✅ **B-0310** — Embedding Text Builder v2 (도서 도메인 풍부화 + 정규화)
- ✅ **B-0311** — Real Embedding via MIS `/v1/embed` (Ingest → MIS batch 호출)
- ✅ **B-0312** — Vector Index Mapping v2 (dim/metric/HNSW) + Alias Wiring
- ✅ **B-0313** — Chunk 기반 Vector Index (옵션): chunk kNN → doc 승격 → RRF fusion
- ✅ **B-0314** — Embedding Cache + 비용 절감 (ingest reuse + query embedding cache)
- ✅ **B-0315** — Offline Eval: Vector/Hybrid 회귀 테스트 (Toy vs Real 비교)
- ✅ **B-0316-mis-real-spell-model-serving**
- ✅ **B-0316** — MIS: Real Embedding Model Loader (replace toy /v1/embed)
- ✅ **B-0317-qs-enable-http-spell-provider-to-mis**
- ✅ **B-0317** — Ingest: use MIS /v1/embed as default embedding provider (with cache + fallback)
- ✅ **B-0318-qs-spell-candidate-generator-and-domain-dict**
- ✅ **B-0318** — Search Service: Embedding HTTP hardening + cache + fallbacks
- ✅ **B-0319-spell-offline-eval-and-quality-loop**
- ✅ **B-0319** — Embedding: offline eval + regression suite (vector quality gate foundation)
- ✅ **B-0320** — MIS: Cross-Encoder ONNX reranker (real model) + routing
- ✅ **B-0321** — Ranking Service: feature parity + explain/debug output
- ✅ **B-0322** — Rerank: guardrails + budget governor (topN/topR/timeout/cost)
- ✅ **B-0323** — Rerank: offline eval + CI gate (quality regression prevention)
- ✅ **B-0320** — MIS Real Spell Model (T5/ONNX) Enablement + Runtime Wiring + Smoke Test
- ✅ **B-0230** — Query Service Endpoint 정렬: /query/prepare 표준화 + /query-context Deprecate
- ✅ **B-0231** — BFF Search Flow: QS 호출을 /query-context → /query/prepare로 전환
- ✅ **B-0232** — Search Service: “나쁜 결과”일 때만 QS /query/enhance로 1회 재검색(2-pass)
- ✅ **B-0233** — Query Service: 통합검색 Understanding(룰 기반) + 명시 필터 구문 파싱(author:/isbn:/series:)
- ✅ **B-0234** — Search Service: QC 기반 필드 라우팅/부스팅 (ISBN/Author/Title/Series) + filters foundation
- ✅ **B-0235** — Contracts 정렬: BFF/SR/QS 요청·응답 스키마 버저닝 + 검증 게이트
- ✅ **B-0237** — OpenSearch: KDC facet/filter 지원 필드 추가 + reindex/alias-swap
- ✅ **B-0239** — Observability: enhance 트리거/재시도 결과/검색 품질 메트릭
- ✅ **B-0240** — 문서/SSOT 정렬: 서비스 책임/README 공백/Outbox Relay·Index Writer·OLAP Loader 위치 명시
- ✅ **B-0336-reranking-optimize**
- ✅ **I-0301** — per-env config (dev/stage/prod) + secret injection/rotation (extensible)
- ✅ **I-0302** — OpenTelemetry end-to-end(trace 연결)
- ✅ **I-0303** — Metrics(SLO: p95/p99, error rate) + Grafana dashboards
- ✅ **I-0304** — 로그 수집/샘플링/보관 정책 (structured logging + correlation)
- ✅ **I-0305** — OLAP 적재(ClickHouse/BigQuery 택1) + 스키마/파티션
- ✅ **I-0306** — Metabase/대시보드(검색/AC/주문 KPI)
- ✅ **I-0307** — MySQL 백업/복구 + DR 리허설 스크립트
- ✅ **I-0308** — OpenSearch 스냅샷/복구 + retention (Index DR)
- ✅ **I-0309** — 부하/성능 테스트 (검색 p99 + 인덱싱 throughput)
- ✅ **I-0310** — E2E 테스트 자동화 (검색→장바구니→주문→결제→배송)
- ✅ **I-0311** — OWASP 기본 + 헤더/CORS/CSRF 전략 (Security Baseline)
- ✅ **I-0312** — Audit Log 강제 + Admin 위험작업 승인(옵션) (Security/Ops)
- ✅ **I-0313** — CI/CD (빌드/테스트/배포) + 환경 분리
- ✅ **I-0315** — Blue/Green/Canary 배포 (서빙 서비스)
- ✅ **I-0316** — Runbook / On-call (장애 대응 절차)
- ✅ **I-0317** — 비용/리소스 가드레일 (알람/오토스케일 정책)
- ✅ **I-0318** — CI에 Offline Eval 게이트 추가 (성능 하락 배포 금지)
- ✅ **I-0320** — 모델 아티팩트 저장/배포 (로컬→오브젝트 스토리지)
- ✅ **I-0321** — MIS 스케일링/리소스 프로파일 (CPU/GPU 옵션) + 오토스케일 기준
- ✅ **I-0330** — Kafka 스키마 전략(Avro/Protobuf) + 호환성 규칙 + DLQ/Replay
- ✅ **I-0340** — Replay 도구(기간 지정 재처리) + DLQ 자동 라우팅
- ✅ **I-0341** — Schema Registry 도입(선택) + 호환성 CI 검사
- ✅ **I-0342** — Chaos/Degrade 리허설(의존 서비스 다운 시나리오) + Runbook 보강
- ✅ **I-0343** — Rate-limit/abuse 패턴 탐지(봇/스크래핑) + 차단 정책
- ✅ **I-0344** — PII 마스킹/로그 정책(필드 레벨) + 보관주기/삭제(선택)
- ✅ **T-0102** — Add Vanilla Vite (React + TS) Web Apps (User + Admin) + .env
- ✅ **T-0103** — Admin UI: Layout Shell + Router + Sidebar (MVP)
- ✅ **T-0105** — Admin: Search Playground E2E (Query Service → Search Service)
- ✅ **T-0106** — Web User: Layout Shell + Router (MVP)
- ✅ **T-0201** — OpenSearch local runtime + seed
- ✅ **T-0210** — Local OpenSearch v1.1: doc/vec indices + aliases + seed
- ✅ **T-0211** — Local OpenSearch v1.1: add ac_suggest + authors/series + aliases + seed
- ✅ **T-0501** — Query Service MVP: /health, /query-context (FastAPI) [DETAILED]
- ✅ **T-0502** — Query Service: Emit QueryContext v1.1 (qc.v1.1) MVP
- ✅ **T-0503** — Query Service: Env-based CORS (dev/staging/prod ready)
- ✅ **T-0602** — Search Service v1.1 Hybrid MVP: lexical + vector + RRF + hydrate (Spring Boot)
- ✅ **T-0701** — Ranking Service MVP: `/health`, `/rerank` (Toy Reranker)
- ✅ **T-0702** — Search Service: call Ranking Service (/rerank) and apply rerank results
- ✅ **T-0802** — Search Service: Accept QueryContext (qc.v1.1) and execute plan (lex/vector/rerank, filters, fallbacks)
- ✅ **U-0107** — Web User: Search Page (MVP) — Query Service → Search Service (qc.v1.1)
- ✅ **U-0108** — Web User: Search Results UX Upgrade (Cards, Filters-lite, Pagination)
- ✅ **U-0109** — Web User: Book detail page + sessionStorage handoff (MVP)
- ✅ **U-0110** — Web User: Search E2E via Query Service (qc.v1.1) → Search Service (/search)
- ✅ **U-0111** — Web User: Book Detail Deep Link (fetch by docId)
- ✅ **U-0112** — Web User: Autocomplete Typeahead (uses **Autocomplete Service**, not Search Service)
- ✅ **U-0113** — Web User: 자동완성 UX 고도화 (Typeahead + 키보드/모바일 + 최근검색)
- ✅ **U-0116** — Web User: 장바구니 UI/UX (Cart)
- ✅ **U-0117** — Web User: Checkout UI (주소/배송/결제수단 선택)
- ✅ **U-0118** — Web User: 결제 플로우 UI (성공/실패/재시도)
- ✅ **U-0119** — Web User: 주문내역/배송조회 UI
- ✅ **U-0120** — Web User: 취소/환불 UI (Cancel/Refund Request)
- ✅ **U-0130** — Web User: API 호출을 BFF로 전환(무중단) (BFF primary + direct fallback)
- ✅ **U-0131** — Web User: Chat UI (RAG, 스트리밍 + 출처 카드 + 근거 보기)
- ✅ **U-0120** — User Web: 통합검색 UI(필터 칩/고급검색) + KDC 카테고리 브라우징
- ✅ **B-0XXX** — Flyway Adoption: Baseline an Existing DB (already created by `scripts/ingest/sql`) and Move to a Single `db/migration` Source
- 🟡 **B-0221** Raw → Canonical transform + Reindex(blue/green) + alias swap
  - DoD: DB canonical row count increases, `books_*` search hits OK, alias switch OK

---

# Phase 2 — BFF introduction + “Front QS direct → BFF” zero-downtime migration

**Goal:** Production-grade API standard (BFF) + gradual front migration (toggle-based) + remove direct-call

## 2-A) BFF / contracts / auth
- ✅ **B-0225** Introduce BFF (Search API) (Spring Boot)
  - `/search` `/autocomplete` `/books/:id` + (add) `/chat`
  - issue request_id/trace_id, fan-out, assemble responses, outbox logging
- ✅ **B-0226** Freeze contract (OpenAPI/JSON Schema) + CI validation (compat gate)
- ✅ **B-0227** AuthN/AuthZ (User/Admin) + rate limit
  - Admin RBAC (admin_role/role_permission), per-API rate limits

## 2-B) Front zero-downtime migration (core)
- ✅ **U-0130** Web User: switch API calls to BFF (zero-downtime)
  1) env toggle: **BFF primary + direct fallback**
  2) unify search/autocomplete/detail/chat via BFF
  - DoD: QS direct removable in prod
- ✅ **A-0120** Web Admin: switch API calls to BFF (zero-downtime)
  - all ops functions (reindex/policies/experiments/products) via BFF
- ✅ **I-0301** per-env config (dev/stage/prod) + secret injection/rotation (extensible)

---

# Phase 2.5 — Reindex/Index Ops service-ization (Deferred)

**Goal:** move reindex/index ops into managed jobs after API migration is stable.

- ✅ **B-0223** Index Writer (reindex job) service-ized (state machine/pause/resume/checkpoint)
- ✅ **B-0223a** Reindex safety nets (throttling/backoff/retry/partial failure)
- ✅ **B-0224** Synonym/Normalization deployment pipeline (versioning/rollback)
- ✅ **A-0113** Ops: Reindex/Job Run UI (job_run/reindex_job/ops_task)

---

# Phase 2.6 — Data “Formal Pipeline” (Deferred)

**Goal:** Flyway schema (v1.1) canonical load + reindex/alias operations + Ops UI

## 2.6-A) Canonical load/upsert/quality
- ✅ **B-0222** Finalize Canonical ETL idempotent/incremental (upsert) (payload_hash based)
- ✅ **B-0221a** Canonical quality validation (ETL data tests)
  - null/duplicate/distribution/schema checks (per ETL stage)
- ✅ **B-0221b** Authority/merge v1 (minimal dedupe for material/agent)
  - minimal handling of material_merge/agent label variants (ops level)

---

# Phase 3 — Autocomplete “Ops Loop” (Redis + Kafka + Aggregation)

**Goal:** p99 protection + CTR/Popularity reflection + ops UI

- ✅ **B-0214** Complete Autocomplete OS-backed suggestions (consistency/alias/error cleanup)
- ✅ **B-0228** AC index/alias strategy (`ac_candidates_v*`, `ac_read`/`ac_write`)
- ✅ **B-0229** Redis hot-prefix cache (TopK) + TTL/size policy
- ✅ **B-0230** AC event emission (`ac_impression`/`ac_select`)
  - recommendation: **BFF(outbox)**
- ✅ **B-0231** AC aggregation consumer (CTR/Popularity → OS/Redis, decay+smoothing)
- ✅ **U-0113** User Web autocomplete UX enhancements (keyboard/mobile/recent search/recommended queries)
- ✅ **A-0106** Admin autocomplete ops screen (boosting/blocked/trends/CTR monitoring)

---

# Phase 4 — Search/Ranking ops loop + QS/SR hardening (incl. hybrid)

**Goal:** close the loop from logs → features → reranking, and make QS/SR resilient to cost/latency/failures  
**Point:** SR tickets must include **Hybrid (BM25+Vector+Fusion/RRF) + degrade + debug**

## 4-A) Events/Transport (Outbox→Kafka)
- ✅ **B-0232** Search event emission (`search_impression`/`click`/`dwell`)
  - include imp_id, position, query_hash, experiment/policy
- ✅ **B-0248** Outbox → Kafka relay (dedup_key idempotent, replay-safe)
- ✅ **I-0330** Kafka schema strategy (choose Avro/Proto) + compat rules + DLQ/Replay

## 4-B) QS (Query Service) hardening (“cost/latency” control)
- ✅ **B-0260** Freeze QueryContext v1 + trace propagation rules end-to-end
- ✅ **B-0261** Enhance Normalize/Detect (NFKC/ICU, initials/volume/ISBN/series, canonicalKey)
- ✅ **B-0262** 2-pass (rewrite/spell/RAG) gating (cost governor)
  - 0 results / low confidence / pattern-based + per-query cooldown/caps
- ✅ **B-0263** Rewrite quality loop (before/after logs + failure case curation)
- ✅ **B-0264** Query cache (optional) (normalize cache + rewrite cache)

## 4-C) SR (Search Service) hardening (“Hybrid/failures/latency/debug”)
- ✅ **B-0266** Retrieval strategy hardening
  - BM25 + filters + **Vector (optional) + Fusion (RRF)** plugin-ized
- ✅ **B-0266a** Decide Query Embedding generation path
  - (option 1) OS-internal model / (option 2) embedding inference (can be absorbed into MIS)
- ✅ **B-0267** Circuit breaker/timeout/hedged + degraded responses (avoid 0 results)
- ✅ **B-0268** Debug/Explain API (Playground integration, score breakdown)
- ✅ **B-0269** SERP cache/Book detail cache (ETag/Cache-Control) for p99 protection

---

# Phase 5 — MIS introduction + Ranking Service operations (advanced)

**Goal:** isolate/scale/version/rollback model inference + safe degrade for RS/SR + debuggable

## 5-A) MIS (Inference Serving) essentials
- ✅ **B-0270** MIS skeleton (stateless inference API)
  - `/ready` `/v1/models` `/v1/score` + concurrency limits/queueing/warmup/timeouts
- ✅ **B-0271** Reranker ONNX Runtime serving (phase 1) + dynamic batching (optional)
- ✅ **B-0272** RS (orchestrator) ↔ MIS contract freeze + load test (batch/latency)
- ✅ **B-0273** SR/RS fallback policy (ops safety)
  - if MIS down, BM25-only / heuristic
- ✅ **B-0274** Model Registry integration (version rollout/rollback/canary routing)
- ✅ **I-0320** Model artifact storage/deployment (object storage)
- ✅ **I-0321** MIS scaling/resource profiles (CPU/GPU options) + autoscale criteria

## 5-B) Ranking Service “advanced” (ops/quality/explainability)
- ✅ **B-0250** Feature fetch layer (online KV) v1 (ctr/popularity/freshness)
- ✅ **B-0251** Feature spec unification (`features.yaml`)
  - enforce identical offline/online transforms (“key to LTR success”)
- ✅ **B-0252** RS debug mode (return features/scores/model version/reason codes)
- ✅ **B-0253** RS cost guardrails (topN limits, conditional rerank, timeout budget)
- ✅ **A-0124** Admin: failure case/rerank debug/replay UI (Playground link)

---

# Phase 6 — LTR pipeline + Offline eval regression tests (deployment gate)

**Goal:** block “performance regressions” in CI automatically

## 6-A) Data/Labels (OLAP)
- ✅ **I-0305** OLAP load (choose ClickHouse/BigQuery) + partitioning/schema
- ✅ **B-0290** Training label generation job (implicit labeling: click/dwell/cart/purchase)
- ✅ **B-0291** minimal position-bias handling (exploration traffic/simple IPS/interleaving)

## 6-B) Features/Aggregation (point-in-time)
- ✅ **B-0292** CTR/Popularity aggregation consumer (time decay/smoothing) → Feature Store update
- ✅ **B-0293** point-in-time correctness (snapshot/time-join design/implementation)

## 6-C) Training/Eval/Gate
- ✅ **B-0294** LTR training pipeline (LightGBM LambdaMART v1) + artifact registration
- ✅ **B-0295** Offline eval runner (regression test)
  - Golden/Shadow/Hard sets + NDCG@10/MRR/Recall@100/0-result-rate/latency proxy
- ✅ **I-0318** Add eval gate to CI (fail on regression vs baseline)
- ✅ **A-0125** Admin: model/metric reports + rollout/rollback UI (model_registry/eval_run)

> Note (ops default): **LTR (cheap 1st stage) + Cross-encoder (expensive 2nd stage)** is the right pattern

---

# Phase 7 — RAG-based AI chatbot (product-grade) + ops loop

**Goal:** include **evidence/reproducibility/trust/feedback loop**, not just “answers”

- ✅ **B-0280** Document collection/normalization/chunking + change detection/incremental updates
- ✅ **B-0281** RAG index (`docs_doc_v*`, `docs_vec_v*`) design (fix highlight/citation keys)
- ✅ **B-0282** QS `/chat` orchestration (Rewrite→Retrieve→Rerank→Generate + enforce citations)
- ✅ **B-0283** LLM Gateway (keys/rate limits/retries/audit/cost control)
- ✅ **B-0284** Chat feedback events/eval pipeline (👍👎/hallucination report/insufficient evidence)
- ✅ **U-0131** User Web Chat UI (streaming + source cards + show evidence)
- ✅ **A-0122** Admin doc/index ops UI (upload/reindex/version/rollback)
- ✅ **A-0123** Admin RAG eval/labeling UI (question sets/answers/evidence judgment)

---

# Phase 8 — Commerce (orders/payments/shipping) “schema v1.1 full implementation”

- ✅ **B-0237** SKU/Offer/current_offer API
- ✅ **B-0238** Inventory balance/ledger transaction rules + concurrency
- ✅ **B-0239** Cart API
- ✅ **B-0240** Order creation + state machine + order_event
- ✅ **B-0241** Payment integration (mock PG → real PG extensible design, idempotency keys/retries)
- ✅ **B-0242** Shipment/Tracking integration
- ✅ **B-0243** Refund/partial refund + inventory restoration (ledger)
- ✅ **U-0116** Cart UI
- ✅ **U-0117** Checkout UI
- ✅ **U-0118** Payment flow UI
- ✅ **U-0119** Order/shipping tracking UI
- ✅ **U-0120** Cancel/refund UI
- ✅ **A-0109** Product ops UI (seller/offer/inventory)
- ✅ **A-0110** Payment/refund ops UI
- ✅ **A-0111** Shipping ops UI (labels/status/issues)

---

# Phase 9 — Observability / Reliability / Security / Release (production essentials)

- ✅ **I-0302** OpenTelemetry end-to-end (trace linkage)
- ✅ **I-0303** Metrics (SLO: p95/p99, error rate) + Grafana
- ✅ **I-0304** Log collection/sampling/retention policy
- ✅ **I-0306** Metabase/dashboard (search/AC/order KPIs)
- ✅ **I-0307** MySQL backup/restore + DR rehearsal
- ✅ **I-0308** OpenSearch snapshot/restore + retention
- ✅ **I-0309** Load/performance tests (p99 + indexing throughput)
- ✅ **I-0310** E2E test automation (search→payment→shipping)
- ✅ **I-0311** OWASP basics + headers/CORS/CSRF
- ✅ **I-0312** Enforce audit_log + Admin risky-action approval (optional)
- ✅ **I-0313** CI/CD (build/test/deploy) + environment separation
- ✅ **I-0315** Blue/Green/Canary deployment (serving services)
- ✅ **I-0316** Runbook/On-call (incident response procedures)
- ✅ **I-0317** Cost/resource guardrails (alerts/autoscale)

---

# Phase 10 — “Further hardening” extra tickets (production polish)

> Phase 1~9 cover “service launch + operations.”  
> The tickets below further raise **performance/quality/operational maturity** (optional, prioritized).

## 10-A) Search quality/consistency hardening (authority/dedup deepening)
- ✅ **B-0300** Material canonical selection (editions/sets/recover) rule hardening + SERP grouping
- ✅ **B-0301** Agent authority (author name variants) normalization hardening + alias dictionary ops
- ✅ **A-0130** Admin: merge/canonical selection/alias ops UI (with audit logs)

## 10-B) Hybrid hardening (vector quality/cost optimization)
- ✅ **B-0302** Query embedding cache/hot query vector cache (cost savings)
- ✅ **B-0303** Fusion policy experiment framework (RRF vs weighted) + experiment integration
- ✅ **B-0304** Chunk→Doc promotion logic hardening (diversity/dedup)

## 10-C) Kafka ops “for real” (reprocessing/accuracy)
- ✅ **I-0340** Replay tool (time-range reprocessing) + DLQ auto routing
- ✅ **B-0305** Event idempotency key standard guide (common across event_type)
- ✅ **I-0341** Schema Registry adoption (optional) + compatibility CI checks

## 10-D) Cost/stability (serving end-to-end)
- ✅ **B-0306** Global budget governor (shared budget for search/chat/rerank)
- ✅ **I-0342** Chaos/degrade rehearsals (dependency down scenarios) + runbook hardening
- ✅ **I-0343** Rate-limit/abuse pattern detection (bots/scraping) + blocking policy

## 10-E) Privacy/security (real service polish)
- ✅ **I-0344** PII masking/log policy (field-level) + retention/deletion (optional)
- ✅ **B-0307** User data export/delete (optional: strong portfolio points)

---

## Phase 11 — Chatbot 안정화/고도화 (NEW Backlog)

**Goal:** “동작은 한다” 수준이 아니라, 실제 운영에서 장애 재현 가능/근거 신뢰 가능/비용 통제 가능 상태로 챗봇 완성

### 11-A) Core reliability / API contracts
- 🟡 **B-0350** Chat 장애 재현 키트 (failure taxonomy + replay seed + deterministic test harness)
  - DoD: 재현 불가 이슈를 `request_id/trace_id + replay payload`로 1회 재현 가능
- 🟡 **B-0351** `/chat` 요청 유효성/한도/타임아웃 표준화 (validation envelope + graceful timeout)
  - DoD: 잘못된 요청/초과 요청/타임아웃이 일관된 오류 코드와 메시지로 반환
- 🟡 **B-0352** Chat degrade 정책 명시화 (LLM 장애 시 search-only fallback + 사유 코드)
  - DoD: LLM/MIS 장애 상황에서도 “빈 응답” 없이 근거 기반 축약 응답 반환

### 11-B) Groundedness / retrieval quality
- 🟡 **B-0353** 근거 강제 게이트 강화 (citation coverage threshold + insufficient-evidence block)
  - DoD: 근거 부족 답변은 차단하고 “근거 부족” 상태로 응답
- 🟡 **B-0354** 다국어 질의 품질 보강 (한글 우선 + CJK 혼합 질의 normalize/rewrite 룰)
  - DoD: 한국어 질의에서 한국어 문서 우선, 혼합 질의 회귀셋 통과
- 🟡 **B-0355** 대화 메모리 정책 v1 (세션 메모리 TTL + PII 최소화 + 요약 저장)
  - DoD: 세션 맥락 유지와 만료가 예측 가능하고 개인정보가 로그/메모리에 과다 저장되지 않음

### 11-C) Safety / policy / evaluation
- 🟡 **B-0356** Prompt injection/jailbreak 방어 체인 (input/output policy + risky tool denylist)
  - DoD: 레드팀 프롬프트셋 기준 차단율 목표 달성, 정상 질의 오탐율 기준 이내
- 🟡 **B-0357** Chat 품질 지표 게이트 (groundedness, hallucination, answer usefulness, abstain precision)
  - DoD: CI에서 핵심 지표 하락 시 배포 차단
- 🟡 **B-0358** 도메인 평가셋 확장 (도서검색/주문/환불/배송/이벤트 안내 시나리오)
  - DoD: 실제 사용자 질문 분포를 반영한 평가셋 버전 관리 + 주기 리포트 자동화

### 11-D) UX / Admin / Ops
- 🟡 **U-0140** Chat UX 안정화 (재시도/중단/이어쓰기/네트워크 복구/스트리밍 끊김 복원)
  - DoD: 브라우저 새로고침/일시 네트워크 단절 후에도 사용자 체감 실패율 감소
- 🟡 **U-0141** 근거 UX 개선 (출처 클릭 점프, 인용 구간 하이라이트, 근거-답변 불일치 경고)
  - DoD: 답변-근거 검증 가능성이 UI에서 명확히 보임
- 🟡 **A-0140** Chat Ops 대시보드 (실패율/타임아웃/근거부족률/할루시네이션 신고율/비용)
  - DoD: 운영자가 5분 내 이상징후 원인 범주를 식별 가능
- 🟡 **A-0141** Prompt/Policy 버전 운영 UI (승인 플로우 + 롤백 + 감사 로그)
  - DoD: 무중단 정책 변경과 즉시 롤백 가능
- 🟡 **I-0350** LLM 비용/쿼터/속도 가드레일 (tenant/user/day budget + alert + auto-throttle)
  - DoD: 비용 폭증/트래픽 급증 상황에서 자동 보호 동작
- 🟡 **I-0351** Chat 장애 런북/온콜 시나리오 강화 (LLM 장애, 벡터 인덱스 장애, Kafka 지연)
  - DoD: 장애 유형별 대응 절차와 복구 검증 체크리스트 문서화/리허설 완료

### 11-E) Advanced Intelligence / Release Safety (추가)
- 🟡 **B-0359** Chat Tool Calling (주문/배송/환불 인텐트는 백엔드 조회형 응답 강제)
  - DoD: 커머스 질의에서 추측 답변 대신 실제 데이터 기반 응답
- 🟡 **B-0360** Answer-Citation Entailment Verifier (2차 정합성 검증)
  - DoD: citation 존재하지만 의미 불일치하는 문장 자동 검출/강등
- 🟡 **B-0361** Query Decomposition + Multi-hop Retrieval (복합질의 분해 검색)
  - DoD: 복합 질문 평가셋에서 recall/groundedness 개선
- 🟡 **B-0362** Consent 기반 개인화 + Explainability 라벨
  - DoD: opt-in 사용자군 usefulness 개선, opt-out 미사용 보장
- 🟡 **U-0142** Chat Quick Actions UX (주문/배송/환불/이벤트 버튼형 처리)
  - DoD: 자주 쓰는 지원 시나리오 완료율 개선
- 🟡 **A-0142** Chat Failure Triage Workbench (Replay + Diff + RCA)
  - DoD: 실패 케이스 RCA 시간 단축
- 🟡 **I-0352** Chat Canary/Shadow/Auto-rollback 게이트
  - DoD: 회귀 배포 자동 차단/롤백

### 11-F) Stateful AI / Governance / Continuous Improvement (추가)
- 🟡 **B-0363** Conversation State Store (checkpoint summary + recovery)
  - DoD: 새로고침/네트워크 단절 후 세션 문맥 복원 성공률 개선
- 🟡 **B-0364** Tool Schema Registry + Permission Policy
  - DoD: 모든 tool 호출 전/후 schema 검증 + 권한 매트릭스 차단 보장
- 🟡 **B-0365** Knowledge Freshness Pipeline (이벤트/공지/정책 최신화)
  - DoD: 변경 반영 SLA 충족, stale answer rate 감소
- 🟡 **B-0366** Real-time Feedback Triage + Prompt Improvement Loop
  - DoD: 고심각도 피드백 triage SLA 충족 + 재발률 개선
- 🟡 **U-0143** Chat Agent Handoff + Guided Forms UX
  - DoD: 챗봇 미해결 케이스에서 상담 전환 이탈률 감소
- 🟡 **A-0143** Chat Experiment Studio (Prompt/Policy A-B)
  - DoD: 안전한 실험-승격-롤백 의사결정 로그를 end-to-end 보존
- 🟡 **I-0353** Chat SLO Guardrails + Auto Remediation
  - DoD: SLO 위반 시 자동 완화/롤백 동작 검증 및 리포트 자동화

### 11-G) Enterprise Reliability / Safety Automation (추가)
- 🟡 **B-0367** Chat Workflow Engine (멀티스텝 커머스 지원)
  - DoD: 주문취소/환불/배송지변경 등 단계형 요청 완료율 개선 + 오실행 감소
- 🟡 **B-0368** Source Trust Scoring + Answer Reliability Label
  - DoD: 저신뢰/오래된 근거 기반 오답률 감소 + 신뢰 레이블 제공
- 🟡 **B-0369** Sensitive Action Guard (이중 확인 + 리스크 정책)
  - DoD: 고위험 액션 무확인 실행 0건, 감사추적 100% 확보
- 🟡 **B-0370** Chat Ticket Integration (접수/상태추적/후속안내)
  - DoD: 챗 미해결 이슈의 티켓 연계 및 상태 조회 end-to-end 제공
- 🟡 **U-0144** Chat Transparency & Reliability Panel UX
  - DoD: 사용자가 답변 신뢰상태/복구상태를 UI에서 즉시 이해 가능
- 🟡 **A-0144** Chat Governance Console (예외/정책 검토)
  - DoD: 정책 예외/차단 사례 triage + 승인/롤백 감사흔적 일원화
- 🟡 **I-0354** Chat Multi-LLM Routing (Failover + Cost Steering)
  - DoD: 제공자 장애/비용 급등 시 자동 라우팅으로 가용성·비용 안정화

### 11-H) Policy Runtime / Scale Resilience / Advanced Safety (추가)
- 🟡 **B-0371** Chat Policy Engine DSL (Intent/Risk/Compliance)
  - DoD: 정책을 선언형 DSL로 관리하고, 요청별 정책평가 trace 재현 가능
- 🟡 **B-0372** Chat Tool Result Cache + Consistency Invalidation
  - DoD: 반복 조회 지연 감소 + stale 캐시 오답 방지
- 🟡 **B-0373** Adversarial Evalset + Korean Safety Regression Gate
  - DoD: 한국어 안전성 회귀를 PR/릴리즈 게이트에서 자동 차단
- 🟡 **B-0374** Reasoning Budget Controller (step/token/tool limits)
  - DoD: 에이전트형 실행의 비용 폭증/무한루프 위험을 제어
- 🟡 **U-0145** Chat Incident Recovery & User Guidance UX
  - DoD: 장애 상황에서 사용자 이탈률 감소 + 재시도/티켓 전환율 개선
- 🟡 **A-0145** Chat Red-team Lab + Safety Campaign Manager
  - DoD: 정기 레드팀 캠페인 실행 및 취약점 대응 리드타임 단축
- 🟡 **I-0355** Chat Priority Queue + Load Shedding + Backpressure
  - DoD: 피크 트래픽에서도 핵심 커머스 인텐트 성공률 유지

### 11-I) Ticket Intelligence / Deterministic Debug / Reliability Ops (추가)
- 🟡 **B-0375** Chat Ticket Triage Classifier + SLA Estimator
  - DoD: 티켓 자동분류 정확도와 SLA 위험 예측 품질을 측정/개선
- 🟡 **B-0376** Chat Case Evidence Pack Generator
  - DoD: 티켓 처리자가 즉시 활용 가능한 증거 패키지 자동 생성
- 🟡 **B-0377** Source Conflict Resolution + Safe Abstention
  - DoD: 상충 출처 상황에서 오답 단정 대신 안전 보류/확인 유도
- 🟡 **B-0378** Deterministic Agent Replay Sandbox + Debug Snapshots
  - DoD: 에이전트형 실패 케이스 재현 시간 단축 + RCA 품질 향상
- 🟡 **U-0146** Chat Ticket Lifecycle Timeline + Escalation UX
  - DoD: 티켓 상태 문의 반복 감소, 에스컬레이션 사용성 개선
- 🟡 **A-0146** Chat Ticket Ops Quality + SLA Command Center
  - DoD: 운영자가 오분류/SLA위험/증거누락을 한 화면에서 관리
- 🟡 **I-0356** Chat Synthetic Journey Monitoring + Auto Drill
  - DoD: 핵심 챗 여정의 조기 장애 탐지 및 자동완화 검증 체계 확보

### 11-J) Privacy Governance / Temporal Reasoning / Transaction Safety (추가)
- 🟡 **B-0379** Chat Conversation Privacy DLP + Retention Enforcement
  - DoD: 실시간 PII 보호 및 보존주기 강제로 개인정보 리스크 감소
- 🟡 **B-0380** Effective-date-aware Policy Answering
  - DoD: 정책/공지 변경 시점 오답률 감소 및 기준일 투명성 확보
- 🟡 **B-0381** Operator-approved Correction Memory
  - DoD: 승인된 교정지식 기반으로 반복 오류 재발률 감소
- 🟡 **B-0382** Tool Transaction Fence + Compensation Orchestrator
  - DoD: 다단계 tool 실행의 부분반영/중복반영 위험 감소
- 🟡 **U-0147** Chat Privacy/Memory/Action Consent Controls UX
  - DoD: 사용자가 개인정보·메모리·민감액션 정책을 직접 제어 가능
- 🟡 **A-0147** Chat Policy Simulator + Blast-radius Lab
  - DoD: 정책 변경 전 영향 시뮬레이션으로 위험 배포 사전 차단
- 🟡 **I-0357** Chat Control-plane Backup/Restore + DR Drills
  - DoD: 정책/설정/세션메타 복구체계 확립 및 DR 목표(RTO/RPO) 검증

### 11-K) Compliance-grade Delivery / Explainability / Drift Safety (추가)
- 🟡 **B-0383** Chat Output Contract Guard + Claim Verifier
  - DoD: 정책/형식/claim 정합성 위반 출력의 사전 차단
- 🟡 **B-0384** Korean Terminology + Style Governance Engine
  - DoD: 한국어 용어/문체 일관성 및 운영 승인 기반 변경 관리
- 🟡 **B-0385** Resolution Knowledge Ingestion from Closed Tickets
  - DoD: 해결 완료 티켓 지식의 안전한 반영으로 반복문의 감소
- 🟡 **B-0386** Prompt Supply-chain Integrity + Signature Verification
  - DoD: 변조 프롬프트/정책 번들 로딩 차단 및 무결성 추적
- 🟡 **U-0148** Chat Decision Explainability + Denial Reason UX
  - DoD: 거절/제한 응답의 사용자 이해도 및 대체경로 전환율 개선
- 🟡 **A-0148** Chat Compliance Evidence Hub + Audit Export
  - DoD: 준수 증빙 집계/내보내기/감사추적을 단일 콘솔에서 제공
- 🟡 **I-0358** Chat Config Drift Detection + Immutable Release Bundles
  - DoD: 환경 드리프트 조기탐지 및 재현 가능한 릴리즈 보장

### 11-L) Risk-adaptive Intelligence / Localized Resilience (추가)
- 🟡 **B-0387** Intent Calibration + Confidence Reliability Model
  - DoD: 과신/과소신뢰 분기 감소 및 confidence 기반 라우팅 품질 향상
- 🟡 **B-0388** Cross-lingual Query Bridge + Korean-priority Grounding
  - DoD: 다국어 혼합 질의에서 한국어 우선 grounded 응답 품질 개선
- 🟡 **B-0389** Tool Health Score + Capability Routing
  - DoD: 건강도/능력 기반 라우팅으로 tool 실패 전파 감소
- 🟡 **B-0390** Answer Risk Banding + Tiered Approval Flow
  - DoD: 고위험 답변 무검증 노출 감소 및 승인 흐름 정착
- 🟡 **U-0149** Chat Risk-state Visualization + User-safe Flow UX
  - DoD: 위험상태 이해도 개선 및 안전 대체경로 전환율 향상
- 🟡 **A-0149** Chat Risk Ops Cockpit + Weekly Governance Review
  - DoD: 주간 거버넌스 루틴으로 위험 대응 리드타임 단축
- 🟡 **I-0359** Traffic Partitioning + Fail-safe Isolation Mode
  - DoD: 국소 장애 격리로 전체 서비스 영향 최소화

---

## “Does this plan cover it?” checklist summary

- ✅ **Launchable search** (Data→OS→Serving) + ✅ **Production BFF/contracts/auth**
- ✅ **Autocomplete ops loop** (Redis/Kafka/Aggregation) + ✅ **Ranking/MIS**
- ✅ **LTR + offline eval gate** (deployment quality assurance)
- ✅ **RAG chatbot (product-grade) baseline** + ✅ **Commerce** + ✅ **Observability/Release/Security**
- ➕ **Phase 11** adds reliability/safety + privacy/compliance + risk-adaptive routing + localized resilience 티켓
- ➕ Phase 10 is optional pro-level hardening

---

## Codex/ChatGPT context sharing (static files)

> Not auto-sharing; the most reliable approach is to keep fixed files in the repo and have both read them.

Recommended fixed files:
- `AGENTS.md` : constitution/principles/ports/ticket rules
- `ARCHITECTURE.md` : service diagrams/flows
- `Plans.md` : this document (roadmap)
- `contracts/` : OpenAPI/JSON Schema
- `docs/RUNBOOK.md`
- `tasks/` : ticket md(backlog/doing/done)

---

## Next: prepare auto ticket generation (Plan → tasks/backlog/*.md)
- Ticket template: **Scope / Non-goals / DoD / Interfaces / DB&Index / Observability / Commands / Files / Codex Prompt**
- Recommended order: Phase 1 → Phase 2 (includes front migration) → Phase 3 → Phase 4 → Phase 5 → Phase 6 …
