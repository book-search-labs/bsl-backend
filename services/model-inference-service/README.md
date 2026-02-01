# Model Inference Service (MIS)

Stateless inference endpoints for rerank/embedding with concurrency limits, queueing, warmup, and optional dynamic batching.

## Endpoints

- `GET /health` — liveness
- `GET /ready` — readiness summary
- `GET /v1/models` — list model registry state
- `POST /v1/score` — score query-document pairs
- `POST /v1/embed` — embedding vectors (batch)
- `POST /embed` — legacy embed alias (dev fallback)

### /v1/score request (contract)
- `contracts/mis-score-request.schema.json`

### /v1/score response (contract)
- `contracts/mis-score-response.schema.json`

### /v1/models response (contract)
- `contracts/mis-models-response.schema.json`

### /v1/embed request (contract)
- `contracts/mis-embed-request.schema.json`

### /v1/embed response (contract)
- `contracts/mis-embed-response.schema.json`

## Configuration (env)

- `MIS_MAX_CONCURRENCY` (default: 4)
- `MIS_MAX_QUEUE` (default: 32)
- `MIS_TIMEOUT_MS` (default: 200)
- `MIS_WARMUP_ENABLED` (default: true)
- `MIS_WARMUP_PAIRS` (default: 4)
- `MIS_BATCH_ENABLED` (default: false)
- `MIS_BATCH_WINDOW_MS` (default: 8)
- `MIS_BATCH_MAX_PAIRS` (default: 128)
- `MIS_MODEL_REGISTRY_PATH` (default: `app/config/model_registry.json`)
- `MIS_REGISTRY_REFRESH_MS` (default: 5000)
- `MIS_MODEL_DIR` (default: `models`)
- `MIS_DEFAULT_TASK` (default: `rerank`)
- `MIS_DEFAULT_MODEL` (default: empty; uses registry active)
- `MIS_DEFAULT_EMBED_MODEL` (default: empty; uses request model or fallback)
- `MIS_EMBED_BACKEND` (default: `toy`)
- `MIS_EMBED_MODEL_ID` (default: `embed_default`)
- `MIS_EMBED_MODEL_PATH` (onnx path)
- `MIS_EMBED_TOKENIZER_PATH` (tokenizer.json path)
- `MIS_EMBED_OUTPUT_NAME` (optional output name override)
- `MIS_EMBED_DIM` (toy default: 768)
- `MIS_EMBED_MAX_LEN` (default: 256)
- `MIS_EMBED_BATCH_SIZE` (default: 64)
- `MIS_EMBED_NORMALIZE` (default: true)
- `MIS_ONNX_PROVIDERS` (default: `CPUExecutionProvider`)

## Model Registry & Artifacts

`app/config/model_registry.json` controls active/canary routing. `artifact_uri` may reference local paths
(`local://...`) or remote object storage (`s3://`, `gs://`, `https://`). Deployment automation should
sync remote artifacts into `MIS_MODEL_DIR` before boot so ONNX loads from local disk.

Example: `MIS_MODEL_DIR=/models` and `artifact_uri=s3://bsl-models/rerank_v1.onnx` → copy to
`/models/rerank_v1.onnx` during deploy.

## Scaling & Resource Profiles

- **CPU profile**: default `MIS_ONNX_PROVIDERS=CPUExecutionProvider`, moderate `MIS_MAX_CONCURRENCY`
  (4-8), optional batching for throughput (`MIS_BATCH_ENABLED=true`).
- **GPU profile**: install `onnxruntime-gpu` and set
  `MIS_ONNX_PROVIDERS=CUDAExecutionProvider,CPUExecutionProvider`. Increase `MIS_BATCH_MAX_PAIRS`
  and tune `MIS_BATCH_WINDOW_MS` for throughput.
- **Autoscale signals**: queue depth (`MIS_MAX_QUEUE` saturation), p95 `/v1/score` latency above budget,
  CPU/GPU utilization sustained, and error rate spikes.

## Load test

```bash
python tools/load_test.py --url http://localhost:8005/v1/score --requests 200 --concurrency 20 --pairs 8
```
