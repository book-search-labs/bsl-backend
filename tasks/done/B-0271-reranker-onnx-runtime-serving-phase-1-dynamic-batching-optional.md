# B-0271 — MIS: Reranker ONNX Runtime 서빙(v1) + (옵션) Dynamic Batching

## Goal
MIS에서 **Cross-Encoder Reranker**를 ONNX Runtime으로 서빙한다(1차).

- 입력: query + candidates(topR) 텍스트
- 출력: candidate별 score + model_version
- 운영형:
  - batch inference 지원
  - max_len, batch_size, topR 상한
  - timeout budget 준수
- (옵션) dynamic batching으로 throughput 개선

## Background
- Cross-encoder는 품질이 좋지만 비싸다.
- ONNX Runtime(CPU)로도 topR=50 정도는 현실적으로 가능(최적화 전제).
- dynamic batching은 QPS가 생겼을 때 효율이 크게 오른다.

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
  - query + (title/author/snippet) 템플릿
  - token budget 초과 시 snippet truncate
- timeout:
  - per request budget (e.g., 200ms)
- fallback:
  - model not ready → 503 retryable

### 4) Performance knobs
- ORT session options:
  - intra/inter threads
  - graph optimization level
- warmup:
  - startup 시 dummy inference N회

### 5) Dynamic batching (optional)
- micro-batching window (e.g., 5~20ms)
- batch max size (e.g., 16)
- fairness: 오래 기다린 요청 우선 처리

## Non-goals
- LTR 모델 서빙(=B-0294 이후 or 별도)
- GPU/TensorRT(Phase10)

## DoD
- ONNX reranker가 MIS에서 score 반환
- topR/max_len/timeout 가드레일 적용
- warmup + 기본 성능 측정 스크립트 포함
- (옵션) dynamic batching 구현/토글 가능

## Codex Prompt
Implement ONNX reranker in MIS:
- Load reranker.onnx + tokenizer at startup, expose POST /v1/score.
- Build input text template and enforce topR/max_len caps with truncation.
- Add warmup and measure latency; expose metrics for latency, batch size, truncation rate.
- Optional: implement dynamic batching with a small batching window and max batch size.
