# B-0274 — Model Registry Integration: Active Version Routing + Canary Rollout/Rollback

## Goal
MIS/RS is based on Model Registry (DB-based).

-  TBD  
- (Optional) canary: routing only for some traffic to new models
- Immediately rollbackable structure when unloading/performance

## Background
- The model changes frequently (learning/tuning/latest).
- “Code distribution” and “model distribution”, the operational difficulty is greatly reduced.
- When pressing rollout/rollback from Admin UI(A-0125), the form reflects immediately.

## Scope
### 1) Registry contract(required)
DB table(fixed):
- `model_registry(model_id, model_type, name, version, artifact_uri, status, traffic_pct, created_at, ...)`
- New  TBD   (Phase6 Link)

Required inquiry API:
- `GET /internal/models/active?type=RERANKER`
- response: active version, canary version(optional), traffic pct, updated at

### Routing Strategy
- News
  - Active model 100%
- canary(optional):
  - hash-based branch:
    - `bucket = hash(session_id or request_id) % 100`
    - bucket < traffic_pct → canary
  - or header override:
    - New  TBD  For Debug/Replay

### 3) Cache & refresh
- model config cache (e.g. 5~30sec)
- Tag:
  - admin update event invalidate(optional)

### 4) Rollback
- canary failure:
  - change traffic pct=0 or active to the previous version
- MIS Side:
  - Keep the service immediately except “not ready” or its model when loading failure

### 5) Observability
- Request rate/latency/timeout/error by model
- canary vs active comparison indicators (available to connect with online experiments in Phase6)

## Non-goals
- Offline eval gate implementation(=B-0295, I-0318)
- Experiment platform completion (A/B framework all)

## DoD
- The model version is available based on RS or MIS model registry
- check if canary traffic pct is routed as ratio
- Fixed specific model with header override
- rollback(traffic pct 0) check immediately
- Finished metrics tagging by model

## Codex Prompt
Integrate model registry routing:
- Implement active/canary model selection based on model_registry with short TTL cache.
- Add deterministic bucketing using session_id/request_id.
- Support header override for model_version.
- Emit metrics labeled by selected model_version and canary flag, and document rollback procedure.
