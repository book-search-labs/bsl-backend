# B-0270 — MIS skeleton: Stateless Inference API (Ready/Models/Score) + Concurrency/Queueue/Timeout

## Goal
Model Inference Service (MIS) is introduced as “operated abstract serving”

- Separate model embedding/rerank from SR/RS**Fill/Sail/rollback** Enable
- Basic Endpoint:
  - `GET /health`, `GET /ready`
  - `GET /v1/models`
  - `POST /v1/score` (rerank scoring)
  - (optional)   TBD   (B-0266a link)
- Payment Terms:
  - Synchronous Limit (bulkhead)
  - Scots Gaelic
  - Timeout/Cans
  - Warm-up/model loading status
  - request id/trace id

## Background
- When the model runs inside the RS, the disability propagation/resource synthesis is severe.
- When separated by MIS:
  - CPU/GPU Resource Profiling
  - Skip to content
  - canary routing/model registry links
  - Convenience Store

## Scope
### skeleton
- Runtime: Python FastAPI
- Process model:
  - Single node
  - Multi-worker
- Config:
  - model path, model type, timeout, max_concurrency, queue_size
  - dev/stage/prod

### 2) Concurrency/Queueue/Backpressure(required)
- semaphore based max in-flight limit
- queue full time 429 or 503 (clear reason)
- timeout 504 + graceful cancel(best-effort)

### 3) Observability (required)
- metrics:
  - qps, inflight, queue_depth
  - latency(p50/p95/p99)
  - timeouts, rejects
- tracing:
  - request_id/trace_id passthrough

### Error contract(Required)
- Standard Error JSON:
  - code, message, retryable, request_id, trace_id
- Enable fallback in RS/SR

## Non-goals
- Implementing a specific model(=B-0271)
- canary routing/model registry(=B-0274)

## DoD
- MIS Floating with standalone, reflecting the model loading status
- /v1/models, /v1/score Spec Fixed + Sample Request Success
- concurrency/queue/timeout operation test (produced overload)
- metrics/tracing/logging Basic mount

## Codex Prompt
Create MIS skeleton:
- Implement /health, /ready, /v1/models, /v1/score endpoints.
- Add semaphore-based concurrency limits and bounded queue with backpressure.
- Implement request timeout handling and standard error schema.
- Add Prometheus metrics (latency, inflight, queue, rejects, timeouts) and trace_id propagation.
