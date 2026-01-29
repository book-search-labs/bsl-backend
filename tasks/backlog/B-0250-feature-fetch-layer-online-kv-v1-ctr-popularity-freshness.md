# B-0250 — Feature Fetch Layer (Online KV) v1: ctr/popularity/freshness

## Goal
Rank/Licensing is required** to create a search query layer**.

- Input: (query, doc id) or doc id
- Output: ctr smooth / popularity / freshness, etc.
- RS/MIS
- point-in-time extends to LTR ticket (B-0293), and the latest value-focused online here

## Background
- When RS is re-ranked with open position scores, the “operate loop (click → line)” is closed.
- Fitching is the core of model serving stability (timeout/cass/fallback required).

## Scope
### 1) Feature keys (v1 minimum)
- doc-level:
  - `popularity_7d`, `popularity_30d`
  - `ctr_doc_7d_smooth` (query-independent)
  - New  TBD  (published at/updated at)
- query-doc level:
  - `ctr_qd_7d_smooth` (key: hash(q_norm) + doc_id)

### 2) Storage option (choose one now, extensible)
- Option A: Redis (Hash or String)
- Option B: MySQL feature table (latency adverse, cache required)
- Option C: OpenSearch side index (feature index) + cache

> v1 Recommended: Redis center + batch mget

### 3) API (internal)
- POST `/internal/features/get`
  - request: { query_hash?, doc_ids[], fields[] }
  - response: { doc_id -> {feature_name: value} }

### 4) Performance rules
- timeout budget: 10~30ms goal
- Batch Fetch
- provided default value(0, small prior) when missed
- circuit breaker: function store, default immediately

### 5) Integration
- RS/MIS uses feature fetch when rerank request processing
- SR is applicable to response feature snapshot in debug mode (optional)

## Non-goals
- offline dataset builder (B-0290~0295)
- point-in-time join (B-0293)

## DoD
- feature store schema/key specification correction + documenting
- batch fetch implementation + cache/timeout/fallback
- (ctr/popularity/freshness)
- It can be reflected in rerank debug by calling in RS

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
