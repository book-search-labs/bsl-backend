# I-0342 — Chaos/Degrade Rehearsal + Runbook Reinforcement

## Goal
“How to keep your hands safe when you’ve been disabled” to practice and document.
- Even if the dependence service is down, the search returns degraded results not less than 0**
- Runbook: Runbook

## Why
- One of the SR/RS/MIS/QS/OS/Kafka, but the entire UX breaks
- The operating system “Sensual drops are allowed, and the full disability is minimized”

## Scope
### 1) Chaos scenario definition (minimum)
- OpenSearch Delay/Partial Failure
- MIS Download (Not available)
- QS 2-pass Timeout/LLM Error
- Kafka Disorder (outbox backlog)
- Redis Disorder (AC cache miss)

### 2) Degrade Policy
- vector off → bm25-only
- rerank off → response to fused orders
- QS 2-pass off
- AC: Switch to OS miss path + boost rate-limit
- Event: Retransmission after loading outbox (restriction)

### 3) Run Rehearsal
- Disorder in stage environment (container stop/latency injection, etc.)
- p95/p99, error rate, 0-result-rate change history

### 4) Runbook update (I-0316 connection)
- “Alam Generation → Action within 5 minutes” checklist
- Toggle location / command / rollback procedure

## Non-goals
- Introducing the complete chaos engineering platform (e.g. Gremlin)

## DoD
- Completed a minimum of 3 disability scenario rehearsal + record results
- Runbook “i.e. action” procedure reflected
- Verify if the degraded response is returned(0 prevent)

## Codex Prompt
Add chaos/degrade drills:
- Define failure scenarios and expected degrade behaviors per service.
- Create simple scripts to simulate outages/latency in stage.
- Update runbook with step-by-step mitigation actions and verify via metrics.
