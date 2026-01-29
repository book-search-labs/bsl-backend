# A-0125 — Admin Model Registry & Metrics Report UI (rollout/rollback)

## Goal
For search/langing/Chatbot model operation**Model registry + assessment indicator + rollout/rollback UI** provided.
- Model registry Registration Model View
- eval run(offline eval) result report
- canary → rollout → rollback job trigger (problem based)

## Background
- LTR/MIS/cross-encoder is the core of “Model Version Operation”.
- If you have an offline eval revolving gate, the operator needs to see and distribute/roll the result.

## Scope
### 1) Model Registry List/Detail
- Model Type: LTR / RERANKER / EMBEDDING / RAG (Expansion)
- Tag:
  - name, version, status(active/candidate/deprecated)
  - artifact_uri, created_at
  - runtime requirements(cpu/gpu), max batch, max len(optional)
- detail: metadata json display

### 2) Eval Report
- eval run list
- metrics:
  - ndcg@10, mrr@10, recall@100, zero_result_rate, latency_proxy
- Price:
  - delta display for baseline
  - gate pass/fail display

### 3) Rollout / Rollback
- canary start(e.g. 5%)
- Rollout(5→25→50→100)
- immediately rollback(previous active)
- Routing based on policy/buckets (optional)

## Non-goals
- eval runner implementation (B-0295)
- MIS Routing Implementation (B-0274)

## Data / API (via BFF)
- `GET /admin/models`
- `GET /admin/models/{model_id}`
- `GET /admin/models/{model_id}/eval-runs`
- `POST /admin/models/{model_id}/rollout` (payload: strategy/canary_pct)
- `POST /admin/models/{model_id}/rollback`

## Persistence (assumed existing)
- model registry, using the eval run table (this is designed for schema)

## Security / Audit
- rollout/rollback to RBAC Force + audit log
- “Approved two risk operations”

## DoD
- The operator confirms the model version and performance change (Delta) at a glance
- canary/rollout/rollback triggerable
- Thank you for visiting our website.

## Codex Prompt
Implement Model Registry/Eval Report/Rollout UI in Admin(React).
Model List/Details, eval metrics comparison, canary/rollout/rollback offers action.
BFF API Enforcement + Apply RBAC + Audit log Prep.
