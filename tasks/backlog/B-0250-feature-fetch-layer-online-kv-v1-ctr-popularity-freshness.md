# B-0250 — Feature Fetch Layer (Online KV) v1: ctr/popularity/freshness

## Goal
랭킹/리랭킹에 필요한 **온라인 피처 조회 레이어**를 만든다.

- 입력: (query, doc_id) 또는 doc_id
- 출력: ctr_smooth / popularity / freshness 등
- RS/MIS가 low-latency로 호출 가능
- point-in-time은 LTR 티켓(B-0293)에서 확장, 여기선 online 최신값 중심

## Background
- RS가 오픈서치 점수만으로 리랭크하면 “운영 루프(클릭→개선)”가 안 닫힌다.
- 피처 조회는 모델 서빙 안정성의 핵심(타임아웃/캐시/fallback 필수).

## Scope
### 1) Feature keys (v1 최소)
- doc-level:
  - `popularity_7d`, `popularity_30d`
  - `ctr_doc_7d_smooth` (query-independent)
  - `freshness_days` (published_at/updated_at에서)
- query-doc level(가능하면):
  - `ctr_qd_7d_smooth` (key: hash(q_norm) + doc_id)

### 2) Storage option (choose one now, extensible)
- Option A: Redis (Hash or String)
- Option B: MySQL feature table (latency 불리, 캐시 필요)
- Option C: OpenSearch side index (feature index) + cache

> v1 권장: Redis 중심 + batch mget

### 3) API (internal)
- POST `/internal/features/get`
  - request: { query_hash?, doc_ids[], fields[] }
  - response: { doc_id -> {feature_name: value} }

### 4) Performance rules
- timeout budget: 10~30ms 목표
- batch fetch 필수
- miss 시 default value 제공(0, small prior)
- circuit breaker: feature store 다운이면 즉시 default

### 5) Integration
- RS/MIS는 rerank 요청 처리 시 feature fetch 사용
- SR은 debug 모드에서 feature snapshot을 응답에 포함 가능(옵션)

## Non-goals
- offline dataset builder (B-0290~0295)
- point-in-time join (B-0293)

## DoD
- feature store schema/키 규격 확정 + 문서화
- batch fetch 구현 + 캐시/타임아웃/fallback
- 기본 피처 3종 이상(ctr/popularity/freshness) 제공
- RS에서 실제로 호출하여 rerank debug에 반영 가능

## Observability
- metrics:
  - feature_fetch_latency_ms
  - feature_fetch_hit_rate
  - feature_fetch_error_total
- logs:
  - request_id, doc_count, timeout_used, fallback_used

## Codex Prompt
Implement Feature Fetch v1:
- Define Redis key schema for doc and query-doc features.
- Implement batch get endpoint with strict timeouts and defaults on miss.
- Add metrics (latency/hit/error) and ensure RS can consume this API.
