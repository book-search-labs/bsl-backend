# A-0124 — Admin Failure Case + Rerank Debug + Replay UI (Search/RAG)

## Goal
Search/Licing/RAG's **Providing operation UI that collects, analyzes, and rehabilitation**.
- 0 results / low confidence / timeout / etc.
- Pipe Step-by-step score breakdown check
- Replayable Debugging Loop

## Background
- Quality issues in operating environments are key to “recurable”
- RS/MIS/LTR tuning will be reduced without failure case.

## Scope
### 1) Failure Case List
- Type News
  - SEARCH_ZERO_RESULTS
  - SEARCH_LOW_CONFIDENCE
  - RERANK_TIMEOUT / MIS_TIMEOUT
  - HYBRID_VECTOR_FAILURE
  - RAG_UNGROUNDED / MISSING_CITATION
- Payment Terms:
  - created_at, request_id, trace_id, session_id
  - query(q_raw/q_norm), filters, pipeline flags
  - error code, latency breakdown

### 2) Failure Case Detail
- Request snapshot
  - query, filters, sort, page/size
  - pipeline config(bm25/hybrid/rrf/rerank model)
- Result snapshot
  - retrieval topN, fusion topM, rerank topK
  - Stage Score/Purity/Utilization Code
- Log link: trace/span, raw json

### 3) Playground (Run)
- Restart operators change parameters:
  - mode: bm25-only / hybrid
  - fusion: rrf / weighted (optional)
  - rerank: off/ltr/cross-encoder (select model version)
  - budgets: topN/topM/topK
- Results comparison:
  - before/after NDCG proxy(simplified), top10 change display

### 4) Replay
- execute request id based replay
- replay results save as “new playground run”

## Non-goals
- SR/RS internal debug implementation (B-0268/B-0252)
- Model Study Pipeline(B-0294)

## Data / API (via BFF)
- `GET /admin/debug/failures?type=...&from=...&to=...`
- `GET /admin/debug/failures/{failure_id}`
- `POST /admin/debug/playground/run`
- `GET /admin/debug/playground/runs/{run_id}`
- `POST /admin/debug/replay?request_id=...`

## Persistence (suggested)
- failure_case(failure_id, type, request_id, trace_id, payload_json, created_at)
- playground_run(run_id, actor_admin_id, config_json, result_json, created_at)

## Security / Audit
- replay/run is an audit log record (operation risk)
- Model version selection requires RBAC permission (optional)

## DoD
- Failure case can be reproduced as request id
- Step-by-step results/replace breakdown can be checked
- You can change the settings and re-run comparison
- RBAC + Audit

## Codex Prompt
Implement Failure Case/Playground/Replay UI in Admin(React).
Provide a playground, request id replay, which will change the pipeline option.
The result shows the breakdown by stage and uses the BFF API only.
