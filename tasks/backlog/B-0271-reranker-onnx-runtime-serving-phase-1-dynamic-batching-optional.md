# B-0271 — MIS: Reranker ONNX Runtime Serving (v1) + Dynamic Batching (optional)

## Goal
Cross-Encoder Reranker

- Input: query + candidates(topR) text
- Output: Score by candidate + model version
- Company News
  - batch inference support
  - max len, batch size, topR
  - timeout budget compliance
- Improve throughput with dynamic batching

## Background
- Cross-encoder is good quality but expensive.
- OnNX Runtime(CPU) is also available to the topR=50 (latest premise).
- Dynamic batching is greatly applied when QPS has come.

## Scope
### 1) Model packaging
- artifact:
  - `reranker.onnx`, `tokenizer.json` or vocab files, config
- model metadata:
  - name, version, dim/max_len, checksum

### 2) API: POST /v1/score
**Request**
- request_id, model(name/version optional), query, candidates[{id, title, author, snippet}]
- options: topR, max_len, return_debug(false)

**Response**
- model_version, scores[{id, score}]
- latency_ms
- (optional) debug: token_count, truncation flags

### 3) Inference rules / guards
- topR hard cap (e.g., 100)
- input truncation:
  - query + (title/author/snippet) template
  - token budget
- timeout:
  - per request budget (e.g., 200ms)
- fallback:
  - model not ready → 503 retryable

### 4) Performance knobs
- ORT session options:
  - intra/inter threads
  - graph optimization level
- warmup:
  - Dummy inference

### 5) Dynamic batching (optional)
- micro-batching window (e.g., 5~20ms)
- batch max size (e.g., 16)
- fairness: long wait request prior treatment

## Non-goals
- LTR Model Serving(=B-0294 or separately)
- GPU/TensorRT(Phase10)

## DoD
- ONNX reranker returns score from MIS
- topR/max len/timeout Guardian Apply
- Warmup + Basic Performance Measurement Script
- (optional) Dynamic batching implementation/toggle possible

## Codex Prompt
Implement ONNX reranker in MIS:
- Load reranker.onnx + tokenizer at startup, expose POST /v1/score.
- Build input text template and enforce topR/max_len caps with truncation.
- Add warmup and measure latency; expose metrics for latency, batch size, truncation rate.
- Optional: implement dynamic batching with a small batching window and max batch size.
