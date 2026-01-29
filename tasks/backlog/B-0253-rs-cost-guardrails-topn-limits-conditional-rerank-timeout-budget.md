# B-0253 — Ranking Cost Guardrails (TopN/TopK budgets + Conditional Rerank)

## Goal
Ranked/Licensing cost is controlled by operating type.

- Number of candidates(topN), topR, return(topK) budget fixed
- (cross-encoder) Open
- Timeout budget + degrade/fallback base mount
- Cost control is possible by “Quarter/Policy” (A/B/FeatureFlag link)

## Background
- Reranking explodes “quality” and “cost/start” at the same time.
- If there is no guardrail, p99 will be locked when traffic is extended, and the model cost is not controlled.

## Scope
### 1) Budget config (env + policy)
- defaults:
  - New  TBD    (Saved in SR but valid for RS)
  - New  TBD   (Yes: 50)
  - New  TBD   (e.g. 20)
  - New  TBD   (e.g. 25)
  - New  TBD   (e.g. 120)
  - New  TBD   (e.g. 180)
- policy overrides:
  - rerank omitting possible according to intent/segment

### 2) Conditional rerank rules (v1)
- rerank running conditions example:
  - `candidates_count >= min_candidates`
  - `query_context.need_rerank >= threshold`
  - `not low_latency_mode`
  - New  TBD   (Option)
- Tag:
  - LTR -only or return to BM25+feature heuristic

### 3) Degrade strategy
- function fetch timeout → continue with default features
- Return to LTR-only (or fused order)
- full timeout over → immediately best-effort results return + reason code

### 4) Safety
- candidate text length/field limit (model input size explosion proof)
- request payload validation + max size limit

## Non-goals
- SR retrieval budget policy (B-0266/0267) implementation itself
- global governor(B-0306) (service common budget)

## DoD
- The budget parameter is managed by config and forced to runtime
- returns degrade results when rerank is executed in condition.
- debug(B-0252)
- check p99 budget operation in loadtest

## Observability
- metrics:
  - rerank_invocations_total{strategy}
  - rerank_skipped_total{reason}
  - rerank_timeout_total
  - rs_degrade_total{reason}
- logs:
  - request_id, topN/topR/topK, strategy, degrade_reason

## Codex Prompt
Add cost guardrails to RS:
- Enforce topN/topR/topK and strict timeouts.
- Implement conditional rerank gating based on query_context + policy.
- Implement degrade paths on feature fetch and MIS inference failures.
- Emit metrics for skipped/timeout/degrade and integrate with debug output.
