# B-0283 — LLM Gateway: Key/Latememory/Release/Process Control (Centralization)

## Goal
The LLM call does not scatter inside QS, but it is centralized with the LLM Gateway layer**.

- API key/secret management
- rate-limit / concurrency limit
- retry/backoff, timeout, circuit breaker
- request/response Audit Log(Intense Information Masking)
- Cost tracking (token/fare estimate) + budget control

## Background
- LLM is the core risk of “security/cost/disability” in operation
- Go to Contents News
  - Key leak risk reduction
  - Copyright © 2019. All rights reserved.
  - Easy to apply degrade policy when obstacles

## Scope
### 1) Internal API
- `POST /internal/llm/chat-completions`
- New  TBD  (Optional, Connectable with B-0266a/Hybrid)

Request Common Meta:
- request_id, trace_id, user_id(optional), purpose(enum: RAG_ANSWER/QUERY_REWRITE/SPELL/…)
- model_name, temperature, max_tokens, timeout_ms

### 2) Policies (required)
- per-purpose budget:
  - rewrite: max tokens lower
  - answer: max tokens middle
- rate limits:
  - per-IP, per-user, per-purpose
- timeouts:
  - hard timeout
- retries:
  - 429/5xx backoff
  - 4xx no-retry

### 3) Audit & Masking (required)
- Price:
  - prompt/response Original text storage options (default off)
  - PII masking rules apply even if stored
- New TBD or otherwise TBD
  - request_id/trace_id, model, tokens, latency, status

### 4) Degrade rules
- gateway circuit open → QS degrade as “Rejection of convergence-based summary only/or response”
- rewrite failure → retrieval progress to the original q

### 5) Observability
- tokens_used, cost_estimate, error_rate, retry_count, latency_p95/p99

## Non-goals
- Admin Cost Dashboard (Extra I-0306/Metabase)
- Complete multi-bender routing (but designed to expand)

## DoD
- Both LLM calls from QS occur only through Gateway
- rate-limit/timeout/retry/circuit
- Save as an auditor (agent meta)
- Token/Cost Index Exposure

## Codex Prompt
Create LLM Gateway module/service:
- Centralize chat-completions (and optionally embeddings) calls with rate limits, retries, timeouts, and circuit breaker.
- Emit audit logs with request_id/trace_id and token/cost estimates, applying masking rules.
- Update QS to call only through this gateway and implement degrade behavior on gateway failures.
