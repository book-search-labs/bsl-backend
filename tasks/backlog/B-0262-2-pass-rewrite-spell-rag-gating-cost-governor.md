# B-0262 — QS 2-pass Gating (cost governor) for spell/rewrite/RAG

## Goal
QS’s expensive step (2-pass: spell/rewrite/(optional)RAG)** Implements “cost governor” to be executed only in the operational cost/paid budget**.

- 2-pass **Prohibition on the flight**
- Trigger Condition + Budget + Cooldown + High End**p99/ Explosion Proof**
- The final adoption can be determined by the SR “pre/after comparison” (safety device)

## Background
- LLM/T5/RAG calls rapidly expand delays and costs
- “0 cases/animals” will be operated only
- In addition, if you take 2-pass repeatedly on the same query, you need to get a reduced cost → cooldown

## Scope
### 1) 2-pass endpoint/input
- POST `/query/enhance`
  - input:
    - `request_id`, `trace_id`
    - `q_norm`, `q_nospace`, `detected`
    - New  TBD   (from SR):   TBD   |   TBD   |   TBD   |   TBD  (option)
    - `signals`:
      - `top_score`, `score_gap`, `oov_ratio`, `token_count`, `latency_budget_ms`
    - New  TBD  (optional): Top candidates for SR(title/author/snippet)

### 2 years Gating Policy
- rule-based v1 (fast/clear)
  - trigger:
    - `reason == ZERO_RESULTS`
    - `reason == HIGH_OOV`
    - `reason == LOW_CONFIDENCE && score_gap < threshold`
    - New  TBD   -> rewrite priority(optional)
    - New  TBD   -> 2-pass skip
  - deny:
    - request budget exhausted
    - cooldown hit
    - repeated identical query too frequently
    - latency_budget_ms too low
- Output:
  - `decision`: RUN | SKIP
  - `strategy`: SPELL_ONLY | REWRITE_ONLY | SPELL_THEN_REWRITE | RAG_REWRITE (optional)
  - `reason_codes`: [..]

### 3) Budget & cooldown (required)
- per-query cooldown:
  - key = `canonicalKey` (from B-0261) or hash(q_norm+locale)
  - store in Redis:
    - last_enhance_at
    - enhance_count_window
- global budget:
  - per-minute / per-5min max enhance calls
  - (Option) token budget / cost budget (linkable with LLM Gateway)
- parameters (env/config):
  - `qs_enhance_max_rps`, `qs_enhance_window`, `qs_enhance_cooldown_sec`
  - `qs_enhance_max_per_query_per_hour`

### 4) Execution plan (when RUN)
- Fixed timeout budget by step:
  - spell: 80ms
  - rewrite/understanding: 250~800ms (when LLM is used)
  - Total: 900ms
- Degrade when failure:
  - spell failure → try rewrite only (Policy)
  - rewrite failure → q norm return + fail reason

## Non-goals
- T5 spell model itself implementation (can be separated by a separate ticket)
- LLM Gateway(B-0283) Implementation (simple interface)

## DoD
- Only the enhance call should pass gating decision
- cooldown/hardened by Redis
- determine/strategy/reason codes included in the response
- Recreated with reason/signals provided by SR
- metrics/logs

## Observability
- metrics:
  - qs_enhance_requests_total{decision,strategy,reason}
  - qs_enhance_skipped_total{skip_reason}
  - qs_enhance_latency_ms{stage}
  - qs_enhance_cooldown_hits_total
- logs:
  - request_id, canonicalKey, decision, strategy, reason_codes

## Codex Prompt
Implement QS enhance gating:
- Add /query/enhance endpoint that takes reason+signals from SR.
- Compute decision (RUN/SKIP) and strategy based on rules + budgets.
- Enforce per-query cooldown + global limits using Redis.
- Return decision/strategy/reason_codes and emit metrics/logs.
