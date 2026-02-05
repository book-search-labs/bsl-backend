# B-0270 — MIS 골격: Stateless Inference API(Ready/Models/Score) + Concurrency/Queue/Timeout

## Goal
Model Inference Service(MIS)를 “운영형 추론 서빙”으로 도입한다.

- SR/RS에서 모델 추론(embedding/rerank)을 분리해 **격리/스케일/롤백** 가능하게
- 기본 엔드포인트:
  - `GET /health`, `GET /ready`
  - `GET /v1/models`
  - `POST /v1/score` (rerank scoring)
  - (optional) `POST /v1/embeddings` (B-0266a 연계)
- 공통 운영 기능:
  - 동시성 제한(bulkhead)
  - 큐잉/백프레셔
  - 타임아웃/캔슬
  - 워밍업/모델 로딩 상태
  - request_id/trace_id 전파

## Background
- RS 내부에 모델 실행이 섞이면 장애 전파/리소스 경합이 심해짐.
- MIS로 분리하면:
  - CPU/GPU 자원 프로파일링
  - 배치 최적화
  - canary routing/model registry 연계
  - 운영/관측성이 좋아짐

## Scope
### 1) Service skeleton (필수)
- Runtime: Python FastAPI(권장) or gRPC(추후)
- Process model:
  - single node에서도 안정적으로 동작
  - multi-worker 고려(uvicorn workers)
- Config:
  - model path, model type, timeout, max_concurrency, queue_size
  - env 기반(dev/stage/prod)

### 2) Concurrency/Queue/Backpressure(필수)
- semaphore 기반 max in-flight 제한
- queue full 시 429 또는 503 (명확한 reason)
- timeout 시 504 + graceful cancel(best-effort)

### 3) Observability(필수)
- metrics:
  - qps, inflight, queue_depth
  - latency(p50/p95/p99)
  - timeouts, rejects
- tracing:
  - request_id/trace_id passthrough

### 4) Error contract(필수)
- 표준 에러 JSON:
  - code, message, retryable, request_id, trace_id
- RS/SR에서 fallback 판단 가능하게

## Non-goals
- 특정 모델 구현(=B-0271)
- canary routing/model registry(=B-0274)

## DoD
- MIS가 standalone으로 뜨고, /ready가 모델 로딩 상태 반영
- /v1/models, /v1/score 스펙 고정 + 샘플 요청 성공
- concurrency/queue/timeout 동작 테스트(부하로 재현)
- metrics/tracing/logging 기본 탑재

## Codex Prompt
Create MIS skeleton:
- Implement /health, /ready, /v1/models, /v1/score endpoints.
- Add semaphore-based concurrency limits and bounded queue with backpressure.
- Implement request timeout handling and standard error schema.
- Add Prometheus metrics (latency, inflight, queue, rejects, timeouts) and trace_id propagation.
