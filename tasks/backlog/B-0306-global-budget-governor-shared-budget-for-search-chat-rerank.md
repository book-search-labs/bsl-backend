# B-0306 — Global budget governor

## Goal
QS/SR/MIS/LLM calls to “budget/required budgets”
- Preventing costs
- Protects p99 delays
- Automatic degrade is made when obstacles.

## Why
- 2-pass(LLM/T5), hybrid embedding, rerank(MIS), RAG generation are all “expensive steps”
- When traffic is increased, cost/degradation can be exploded outside linear → budget management needs

## Scope
### 1) Budget Model Definition
Requests for Budget:
- `max_total_ms`
- <% if (imgObj.width >= imgObj.height) { %>
  - qs_prepare, qs_enhance, bm25, embedding, knn, fusion, rerank, generate
- <% if (imgObj.width >= imgObj.height) { %>
  - rerank topR cap, 2-pass call cap, retrieve topN cap
- Cost Budget (optional):
  - `max_llm_tokens`, `max_llm_cost_usd`

### 2 years ) Budget Determining Job
Input Signal:
- request mode(search/chat)
- user tier(name/login/admin)
- experiment bucket
- system health (whether it grows)

Price:
- policy-based default + runtime adjustment ("health-based")

### 3) Application point
- BFF:
  - Calculate budget when starting request (header or body)
- QS:
  - 2-pass gate(B-0262)
- SR:
  - topN/topR, embedding/knn Determination based on budget whether calling
- MIS/LLM Gateway:
  - concurrency/queue/timeouts/token cap enforcement

### 4 days ago Degrade Policy (required)
Step-by-step reduction in excess of budget/zone failure:
- rerank failure → response to fused order
- bm25-only
- qs enhance failure → 1-pass only
- chat generate failed → “Source-based search results + summary invalid” fallback

### 5) Observability
- budget config
- “budget exceeded” counter by stage
- degrade rate, llm_call_rate, rerank_call_rate
- Cost estimate (token/export based) Dashboard

## Non-goals
- Automated Tracking Systems
- Real-time payment and payment integration

## DoD
- BFF→QS/SR/MIS/LLM
- Degrade automatically works when exceeding budget/disabled(0 times/timeout prevention)
- metrics are observed in call rate/reduction rate/reduction impact
- In the hot traffic situation, the cost is controlled

## Codex Prompt
Implement global budget governor:
- Define a budget schema (time, calls, token/cost caps) and propagate it from BFF to QS/SR/MIS/LLM gateway.
- Enforce budget at each stage: 2-pass gating, retrieval topN/topR caps, embedding/knn toggles, rerank/generate limits.
- Add degrade policies for partial failures and budget overruns and expose metrics for exceed/degrade rates.
- Provide minimal integration tests demonstrating degrade behavior under forced timeouts.
