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

## “Does this plan cover it?” checklist summary

- ✅ **Launchable search** (Data→OS→Serving) + ✅ **Production BFF/contracts/auth**
- ✅ **Autocomplete ops loop** (Redis/Kafka/Aggregation) + ✅ **Ranking/MIS**
- ✅ **LTR + offline eval gate** (deployment quality assurance)
- ✅ **RAG chatbot (product-grade)** + ✅ **Commerce** + ✅ **Observability/Release/Security**
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
