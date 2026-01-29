# B-0272 — RS(orchestrator) ↔ MIS contract fixed + load test (batch/latency) + Canary-ready

## Goal
Ranked Service (RS) Fixed the contract (Contract) to call MIS stably,
**Return test/Return test**

- RS concentrating on syntion/feature assembly
- MIS focuses on inference (embedding/rerank)
- If the contract is broken, stop at CI (compat gate link B-0226)

## Background
- “Model server” is often changed (version/latest/schedule).
- RS↔MIS does not fix the contract, and there is a failure during operation.
- SR is degrade when over latency budget, so performance tests are required.

## Scope
### 1) Contract definition
- OpenAPI(or JSON Schema)
  - `/v1/score` req/res
  - Skimming
  - Model List( TBD  )
- versioning:
  - major/minor rules
  - Disconnecting change

### 2) RS integration
- In RS:
  - candidate topR preparation (field limit + best chunk included)
  - MIS call timeout setting
  - fallback rule when failure(maintain original order without point)
- request id/trace id

### 3) Load test suite (required)
- tool:
  - k6 / locust / vegeta threesome 1
- Skills News
  - topR=20/50/100
  - Persimmonity 1/5/20/50
  - timeout bound test
- Payment Terms:
  - p50/p95/p99 latency
  - error rate
  - throughput
  - CPU/RAM usage (simplified record)

### 4) Canary-ready hooks
-  TBD   can be specified in request
- or header   TBD  
- (Real routing B-0274)

## Non-goals
- Implementation of Model Registry Routing(=B-0274)
- SR fallback full policy(=B-0273)

## DoD
- RS↔MIS contract file exists in repo and validated in CI
- RS + timeout + fallback processing completed
- Load Test Report (Markdown)
- latency budget stipulated (includes knobs guide in the standard migration)

## Codex Prompt
Lock RS↔MIS contract and performance:
- Define OpenAPI/JSON schema for /v1/score and error responses.
- Integrate RS to call MIS with strict timeouts and propagate request_id/trace_id.
- Add k6/locust load test scenarios for topR=20/50/100 and concurrency sweeps.
- Produce a markdown report with p50/p95/p99, error rate, and resource notes.
