# B-0252 — Ranking Service Debug Mode (Explain + Replay-ready)

## Goal
The ranking service (RS) provides a "explain" option to operate and debug "Why this order is out"

- // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // //
- We use cookies to ensure that we give you the best experience on our website. If you continue to use this site we will assume that you are happy with it.OkPrivacy policy
- Based on creating “replay” in Admin Playground(A-0124)

## Background
- LTR/Reranking issue:
  - A strange result suddenly in a specific query (quality regression)
  - Error missing/default fallback
  - This is a special model version.
- If you don’t have a debug mode, you’ll only be corrected, and you’ll end up.

## Scope
### 1) API surface (internal)
- POST `/internal/rank`
  - request: { request_id, query_context, candidates[], policy, debug? }
  - response: { ranked[], debug? }

### 2) Debug payload (when debug=true)
- request-level
  - `model`: { type, name, version, artifact_id }
  - `feature_set_version`
  - `policy`: { rerank_strategy, topN, topK, timeouts }
  - `latency_ms`: { feature_fetch, model_infer, total }
  - `fallback_used`: boolean + reason
- item-level (topK or topR)
  - `doc_id`
  - `scores`: { base_score?, ltr_score?, ce_score? }
  - New  TBD  : { f1: v, f2: v, ... }
  - `missing_features`: [..]
  - `reason_codes`: [ "FEATURE_FALLBACK", "MODEL_TIMEOUT", ... ]

> Personal information/reduction information is never included.

### 3) Debug output size controls
- debug debug:
  - New  TBD   (Yes: 50)
  - New  TBD   (e.g. 30)
  - Default is only a summary, detailed in the options field

### 4) Replay readiness
- Enable reproduction of the same request:
  - request hash
  - candidate snapshot hash
  - spec version history
- "replay" button in Admin can retransmit such payload

## Non-goals
- Model Learning/Evaluation Pipeline(B-0294/0295)
- Admin UI implementation (A-0124) itself

## DoD
- debug payload on/off
- model/spec/policy/version included in debug
- item-level breakdown
- Debug mode also apply the same timeout/setbrake policy
- Sample replay payload provided on docs

## Observability
- metrics:
  - rs_debug_requests_total
  - rs_debug_payload_bytes (histogram)
  - rs_missing_features_total{feature}
- logs:
  - request_id, model_version, spec_version, fallback_reason

## Codex Prompt
Implement RS debug mode:
- Extend rank response with debug block when debug=true.
- Include model/spec/policy versions, per-stage latency, fallback flags.
- Include per-item score breakdown + missing features (bounded).
- Add payload size guards and docs with a replay example JSON.
