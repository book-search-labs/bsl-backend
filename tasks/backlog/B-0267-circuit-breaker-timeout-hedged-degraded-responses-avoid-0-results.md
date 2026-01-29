# B-0267 — SR Reliability: Circuit Breaker / Timeout / Hedged + Degraded Response (Not available)

## Goal
Search Service is made by the operational type.

- <% if (imgObj.width >= imgObj.height) { %>
- Circuit Breaker + Bulkhead
- hedged request(optional): Run secondary path when slowing
- partial failures**best-effort results** Returns(0 prevent)
- degrade reason response / log / record on event

## Background
- hybrid pipelines are more dependable and fails.
- In operation, it is important to “unfinished results” than “unload response and record degrade”.

## Scope
### 1) Timeout budgets (example defaults)
- bm25: 80~120ms
- embedding: 20~60ms
- knn: 120~200ms
- rerank: 120~250ms
- Total: 250~400ms

### 2) Circuit breaker + bulkhead
- downstream:
  - OpenSearch, MIS(embeddings/rerank), RS, etc.
- Gallery News
  - failure rate threshold
  - open state cooldown
  - half-open probes
- bulkhead:
  - Simultaneous request restriction (quering or fail-fast)

### 3) Degrade rules (must-have)
- bm25-only
- rerank failure → return to fused order
- bm25 failed but vector success → vector-only(when possible)
- Both failed → minimum fallback:
  - Recent Popular/Trend(option) or empty results + "degraded=true" (However, 0 prevention is recommended fallback)

### 4) Hedged request (optional)
- bm25 is timeout nearing:
  - simple bm25 query(field/filter minify) execution
- Effect: Tail latency(p99) reduction target

### 5) Response / Debug annotation
- response.pipeline:
  - `degraded`: true/false
  - `degrade_reasons`: [..]
  - `stages`: { bm25: ok/timeout/fail, vector: ..., rerank: ... }

## Non-goals
- OpenTelemetry Full Set(I-0302)
- RS cost Guardian(B-0253) (currently, SR perspective)

## DoD
- stage timeout application (default value + config)
- Downstream Circuit Breaker + Bulkhead Coverage
- degrade policy implementation + show results
- chaos scenario testing:
  - MIS down, OS slow, RS timeout, etc. "Return response + reason record" check

## Observability
- metrics:
  - sr_stage_timeout_total{stage}
  - sr_circuit_open_total{downstream}
  - sr_degraded_total{reason}
  - sr_partial_success_total
- logs:
  - request_id, degrade_reasons, stage_status, latency breakdown

## Codex Prompt
Make SR reliable:
- Add per-stage timeouts and total budget enforcement.
- Add circuit breakers + bulkheads for OS/MIS/RS.
- Implement degrade policies (bm25-only, fused-only) with reason codes.
- Annotate response.pipeline with stage status and degrade reasons.
- Add chaos tests/simulations for dependency failures.
