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

- ✅ **B-0201 ~ B-0211**: OpenSearch indices/templates/bootstrap
- ✅ **B-0212**: Book detail by docId
- ✅ **B-0213**: Autocomplete API v1
- 🟡 **B-0214**: OS-backed suggestions (TODO)
- ✅ **B-0220**: NLK raw ingest(large-scale streaming) + MySQL/OS smoke
- ✅ **U-0107~0112**, ✅ **A-0102/0103/0105**: Web User/Admin initial screens + **QS direct-call integration (current)**
- 🟡 **B-0221** Raw → Canonical transform + Reindex(blue/green) + alias swap
  - DoD: DB canonical row count increases, `books_*` search hits OK, alias switch OK

---

# Phase 2 — BFF introduction + “Front QS direct → BFF” zero-downtime migration

**Goal:** Production-grade API standard (BFF) + gradual front migration (toggle-based) + remove direct-call

## 2-A) BFF / contracts / auth
- 🟡 **B-0225** Introduce BFF (Search API) (Spring Boot)
  - `/search` `/autocomplete` `/books/:id` + (add) `/chat`
  - issue request_id/trace_id, fan-out, assemble responses, outbox logging
- 🟡 **B-0226** Freeze contract (OpenAPI/JSON Schema) + CI validation (compat gate)
- 🟡 **B-0227** AuthN/AuthZ (User/Admin) + rate limit
  - Admin RBAC (admin_role/role_permission), per-API rate limits

## 2-B) Front zero-downtime migration (core)
- 🟡 **U-0130** Web User: switch API calls to BFF (zero-downtime)
  1) env toggle: **BFF primary + direct fallback**
  2) unify search/autocomplete/detail/chat via BFF
  - DoD: QS direct removable in prod
- 🟡 **A-0120** Web Admin: switch API calls to BFF (zero-downtime)
  - all ops functions (reindex/policies/experiments/products) via BFF
- 🟡 **I-0301** per-env config (dev/stage/prod) + secret injection/rotation (extensible)

---

# Phase 2.5 — Reindex/Index Ops service-ization (Deferred)

**Goal:** move reindex/index ops into managed jobs after API migration is stable.

- 🟡 **B-0223** Index Writer (reindex job) service-ized (state machine/pause/resume/checkpoint)
- 🟡 **B-0223a** Reindex safety nets (throttling/backoff/retry/partial failure)
- 🟡 **B-0224** Synonym/Normalization deployment pipeline (versioning/rollback)
- 🟡 **A-0113** Ops: Reindex/Job Run UI (job_run/reindex_job/ops_task)

---

# Phase 2.6 — Data “Formal Pipeline” (Deferred)

**Goal:** Flyway schema (v1.1) canonical load + reindex/alias operations + Ops UI

## 2.6-A) Canonical load/upsert/quality
- 🟡 **B-0222** Finalize Canonical ETL idempotent/incremental (upsert) (payload_hash based)
- 🟡 **B-0221a** Canonical quality validation (ETL data tests)
  - null/duplicate/distribution/schema checks (per ETL stage)
- 🟡 **B-0221b** Authority/merge v1 (minimal dedupe for material/agent)
  - minimal handling of material_merge/agent label variants (ops level)

---

# Phase 3 — Autocomplete “Ops Loop” (Redis + Kafka + Aggregation)

**Goal:** p99 protection + CTR/Popularity reflection + ops UI

- 🟡 **B-0214** Complete Autocomplete OS-backed suggestions (consistency/alias/error cleanup)
- 🟡 **B-0228** AC index/alias strategy (`ac_candidates_v*`, `ac_read`/`ac_write`)
- 🟡 **B-0229** Redis hot-prefix cache (TopK) + TTL/size policy
- 🟡 **B-0230** AC event emission (`ac_impression`/`ac_select`)
  - recommendation: **BFF(outbox)**
- 🟡 **B-0231** AC aggregation consumer (CTR/Popularity → OS/Redis, decay+smoothing)
- 🟡 **U-0113** User Web autocomplete UX enhancements (keyboard/mobile/recent search/recommended queries)
- 🟡 **A-0106** Admin autocomplete ops screen (boosting/blocked/trends/CTR monitoring)

---

# Phase 4 — Search/Ranking ops loop + QS/SR hardening (incl. hybrid)

**Goal:** close the loop from logs → features → reranking, and make QS/SR resilient to cost/latency/failures  
**Point:** SR tickets must include **Hybrid (BM25+Vector+Fusion/RRF) + degrade + debug**

## 4-A) Events/Transport (Outbox→Kafka)
- 🟡 **B-0232** Search event emission (`search_impression`/`click`/`dwell`)
  - include imp_id, position, query_hash, experiment/policy
- 🟡 **B-0248** Outbox → Kafka relay (dedup_key idempotent, replay-safe)
- 🟡 **I-0330** Kafka schema strategy (choose Avro/Proto) + compat rules + DLQ/Replay

## 4-B) QS (Query Service) hardening (“cost/latency” control)
- 🟡 **B-0260** Freeze QueryContext v1 + trace propagation rules end-to-end
- 🟡 **B-0261** Enhance Normalize/Detect (NFKC/ICU, initials/volume/ISBN/series, canonicalKey)
- 🟡 **B-0262** 2-pass (rewrite/spell/RAG) gating (cost governor)
  - 0 results / low confidence / pattern-based + per-query cooldown/caps
- 🟡 **B-0263** Rewrite quality loop (before/after logs + failure case curation)
- 🟡 **B-0264** Query cache (optional) (normalize cache + rewrite cache)

## 4-C) SR (Search Service) hardening (“Hybrid/failures/latency/debug”)
- 🟡 **B-0266** Retrieval strategy hardening
  - BM25 + filters + **Vector (optional) + Fusion (RRF)** plugin-ized
- 🟡 **B-0266a** Decide Query Embedding generation path
  - (option 1) OS-internal model / (option 2) embedding inference (can be absorbed into MIS)
- 🟡 **B-0267** Circuit breaker/timeout/hedged + degraded responses (avoid 0 results)
- 🟡 **B-0268** Debug/Explain API (Playground integration, score breakdown)
- 🟡 **B-0269** SERP cache/Book detail cache (ETag/Cache-Control) for p99 protection

---

# Phase 5 — MIS introduction + Ranking Service operations (advanced)

**Goal:** isolate/scale/version/rollback model inference + safe degrade for RS/SR + debuggable

## 5-A) MIS (Inference Serving) essentials
- 🟡 **B-0270** MIS skeleton (stateless inference API)
  - `/ready` `/v1/models` `/v1/score` + concurrency limits/queueing/warmup/timeouts
- 🟡 **B-0271** Reranker ONNX Runtime serving (phase 1) + dynamic batching (optional)
- 🟡 **B-0272** RS (orchestrator) ↔ MIS contract freeze + load test (batch/latency)
- 🟡 **B-0273** SR/RS fallback policy (ops safety)
  - if MIS down, BM25-only / heuristic
- 🟡 **B-0274** Model Registry integration (version rollout/rollback/canary routing)
- 🟡 **I-0320** Model artifact storage/deployment (object storage)
- 🟡 **I-0321** MIS scaling/resource profiles (CPU/GPU options) + autoscale criteria

## 5-B) Ranking Service “advanced” (ops/quality/explainability)
- 🟡 **B-0250** Feature fetch layer (online KV) v1 (ctr/popularity/freshness)
- 🟡 **B-0251** Feature spec unification (`features.yaml`)
  - enforce identical offline/online transforms (“key to LTR success”)
- 🟡 **B-0252** RS debug mode (return features/scores/model version/reason codes)
- 🟡 **B-0253** RS cost guardrails (topN limits, conditional rerank, timeout budget)
- 🟡 **A-0124** Admin: failure case/rerank debug/replay UI (Playground link)

---

# Phase 6 — LTR pipeline + Offline eval regression tests (deployment gate)

**Goal:** block “performance regressions” in CI automatically

## 6-A) Data/Labels (OLAP)
- 🟡 **I-0305** OLAP load (choose ClickHouse/BigQuery) + partitioning/schema
- 🟡 **B-0290** Training label generation job (implicit labeling: click/dwell/cart/purchase)
- 🟡 **B-0291** minimal position-bias handling (exploration traffic/simple IPS/interleaving)

## 6-B) Features/Aggregation (point-in-time)
- 🟡 **B-0292** CTR/Popularity aggregation consumer (time decay/smoothing) → Feature Store update
- 🟡 **B-0293** point-in-time correctness (snapshot/time-join design/implementation)

## 6-C) Training/Eval/Gate
- 🟡 **B-0294** LTR training pipeline (LightGBM LambdaMART v1) + artifact registration
- 🟡 **B-0295** Offline eval runner (regression test)
  - Golden/Shadow/Hard sets + NDCG@10/MRR/Recall@100/0-result-rate/latency proxy
- 🟡 **I-0318** Add eval gate to CI (fail on regression vs baseline)
- 🟡 **A-0125** Admin: model/metric reports + rollout/rollback UI (model_registry/eval_run)

> Note (ops default): **LTR (cheap 1st stage) + Cross-encoder (expensive 2nd stage)** is the right pattern

---

# Phase 7 — RAG-based AI chatbot (product-grade) + ops loop

**Goal:** include **evidence/reproducibility/trust/feedback loop**, not just “answers”

- 🟡 **B-0280** Document collection/normalization/chunking + change detection/incremental updates
- 🟡 **B-0281** RAG index (`docs_doc_v*`, `docs_vec_v*`) design (fix highlight/citation keys)
- 🟡 **B-0282** QS `/chat` orchestration (Rewrite→Retrieve→Rerank→Generate + enforce citations)
- 🟡 **B-0283** LLM Gateway (keys/rate limits/retries/audit/cost control)
- 🟡 **B-0284** Chat feedback events/eval pipeline (👍👎/hallucination report/insufficient evidence)
- 🟡 **U-0131** User Web Chat UI (streaming + source cards + show evidence)
- 🟡 **A-0122** Admin doc/index ops UI (upload/reindex/version/rollback)
- 🟡 **A-0123** Admin RAG eval/labeling UI (question sets/answers/evidence judgment)

---

# Phase 8 — Commerce (orders/payments/shipping) “schema v1.1 full implementation”

- 🟡 **B-0237** SKU/Offer/current_offer API
- 🟡 **B-0238** Inventory balance/ledger transaction rules + concurrency
- 🟡 **B-0239** Cart API
- 🟡 **B-0240** Order creation + state machine + order_event
- 🟡 **B-0241** Payment integration (mock PG → real PG extensible design, idempotency keys/retries)
- 🟡 **B-0242** Shipment/Tracking integration
- 🟡 **B-0243** Refund/partial refund + inventory restoration (ledger)
- 🟡 **U-0116** Cart UI
- 🟡 **U-0117** Checkout UI
- 🟡 **U-0118** Payment flow UI
- 🟡 **U-0119** Order/shipping tracking UI
- 🟡 **U-0120** Cancel/refund UI
- 🟡 **A-0109** Product ops UI (seller/offer/inventory)
- 🟡 **A-0110** Payment/refund ops UI
- 🟡 **A-0111** Shipping ops UI (labels/status/issues)

---

# Phase 9 — Observability / Reliability / Security / Release (production essentials)

- 🟡 **I-0302** OpenTelemetry end-to-end (trace linkage)
- 🟡 **I-0303** Metrics (SLO: p95/p99, error rate) + Grafana
- 🟡 **I-0304** Log collection/sampling/retention policy
- 🟡 **I-0306** Metabase/dashboard (search/AC/order KPIs)
- 🟡 **I-0307** MySQL backup/restore + DR rehearsal
- 🟡 **I-0308** OpenSearch snapshot/restore + retention
- 🟡 **I-0309** Load/performance tests (p99 + indexing throughput)
- 🟡 **I-0310** E2E test automation (search→payment→shipping)
- 🟡 **I-0311** OWASP basics + headers/CORS/CSRF
- 🟡 **I-0312** Enforce audit_log + Admin risky-action approval (optional)
- 🟡 **I-0313** CI/CD (build/test/deploy) + environment separation
- 🟡 **I-0315** Blue/Green/Canary deployment (serving services)
- 🟡 **I-0316** Runbook/On-call (incident response procedures)
- 🟡 **I-0317** Cost/resource guardrails (alerts/autoscale)

---

# Phase 10 — “Further hardening” extra tickets (production polish)

> Phase 1~9 cover “service launch + operations.”  
> The tickets below further raise **performance/quality/operational maturity** (optional, prioritized).

## 10-A) Search quality/consistency hardening (authority/dedup deepening)
- 🟡 **B-0300** Material canonical selection (editions/sets/recover) rule hardening + SERP grouping
- 🟡 **B-0301** Agent authority (author name variants) normalization hardening + alias dictionary ops
- 🟡 **A-0130** Admin: merge/canonical selection/alias ops UI (with audit logs)

## 10-B) Hybrid hardening (vector quality/cost optimization)
- 🟡 **B-0302** Query embedding cache/hot query vector cache (cost savings)
- 🟡 **B-0303** Fusion policy experiment framework (RRF vs weighted) + experiment integration
- 🟡 **B-0304** Chunk→Doc promotion logic hardening (diversity/dedup)

## 10-C) Kafka ops “for real” (reprocessing/accuracy)
- 🟡 **I-0340** Replay tool (time-range reprocessing) + DLQ auto routing
- 🟡 **B-0305** Event idempotency key standard guide (common across event_type)
- 🟡 **I-0341** Schema Registry adoption (optional) + compatibility CI checks

## 10-D) Cost/stability (serving end-to-end)
- 🟡 **B-0306** Global budget governor (shared budget for search/chat/rerank)
- 🟡 **I-0342** Chaos/degrade rehearsals (dependency down scenarios) + runbook hardening
- 🟡 **I-0343** Rate-limit/abuse pattern detection (bots/scraping) + blocking policy

## 10-E) Privacy/security (real service polish)
- 🟡 **I-0344** PII masking/log policy (field-level) + retention/deletion (optional)
- 🟡 **B-0307** User data export/delete (optional: strong portfolio points)

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
