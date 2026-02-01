# B-0316 — MIS: Real Embedding Model Loader (replace toy /v1/embed)

## Goal
현재 MIS의 `/v1/embed`가 **toy embedding(결정론적 랜덤 벡터)**만 반환하는 상태다.
이를 **실제 임베딩 모델**(프로덕션급)로 교체하여,
- Search Service / Ingest가 생성하는 벡터 품질을 크게 올리고
- 모델 버전/롤백/로드/워밍업이 가능한 형태로 만든다.

## Why
- 지금 벡터 품질이 조잡해서 Hybrid/Vector retrieval 품질이 제한됨.
- toy 방식은 “일관성”만 제공하고 의미적 유사도는 제공하지 못함.
- MIS는 이미 ONNX 기반 rerank 로더 구조가 있으므로 embed도 동일 패턴으로 “모델 서빙”을 완성해야 함.

## Scope
### In-scope
1) MIS에 **임베딩 모델 로드/서빙** 구현
- 모델 타입: 1차는 **Sentence Transformers 계열** 또는 **BGE/E5 계열**(CPU/ONNX 우선)
- 모델 로딩: startup 시 로드 + warmup
- 동시성 제한 / 큐잉 / timeout 적용(기존 RequestLimiter 재사용)
- batch embed 지원(`/v1/embed`의 texts[])

2) `/v1/embed` 응답 스키마 고정 + 품질 옵션
- `normalize`(L2 norm) 지원
- `dim` 반환
- `model`은 “label”이 아니라 **실제 로드된 모델 선택**에 사용

3) 설정/환경변수 정리
- `MIS_EMBED_BACKEND=toy|onnx|hf` (권장)
- `MIS_EMBED_MODEL_ID` (예: bge-m3, e5-large 등)
- `MIS_EMBED_DIM` (가능하면 자동 추론)
- `MIS_EMBED_NORMALIZE_DEFAULT=true`
- `MIS_EMBED_DEVICE=cpu|cuda` (가능하면)
- `MIS_EMBED_BATCH_SIZE`, `MIS_EMBED_MAX_LEN`

4) 간단 벤치/스모크 테스트
- 같은 입력 -> 같은 벡터(결정론)
- 유사 문장 -> cosine 유사도 상승 확인
- latency/throughput 로그

### Out-of-scope (이번 티켓에서 하지 않음)
- 모델 레지스트리 기반 canary routing(추후 B-0274 범위)
- GPU 최적화(TensorRT 등) 심화
- 멀티 모델 동시 로드(1개 active로 시작)

## Interfaces
### Endpoint
- `POST /v1/embed`
  - Request: `{ "request_id": "...", "model": "bge-m3", "normalize": true, "texts": ["..."] }`
  - Response: `{ "request_id":"...", "model":"bge-m3", "dim":1024, "vectors":[[...],[...]] }`

### Contracts
- `contracts/mis-embed-request.schema.json`
- `contracts/mis-embed-response.schema.json`
- examples 업데이트

## Implementation Notes
- 우선순위: **ONNX Runtime 기반** 임베딩(배포/성능/운영 난이도 낮음)
- 텍스트 정규화는 호출자가 하되, MIS도 최소한의 `strip`/empty validation은 수행
- 대량 요청은 batching으로 처리하되, 너무 큰 batch는 reject(413 또는 400)

## Observability
- metrics
  - `mis_embed_requests_total{status,model}`
  - `mis_embed_latency_ms_bucket{model}`
  - `mis_embed_batch_size_histogram`
  - `mis_embed_queue_depth`
- logs
  - request_id/trace_id 포함
  - model_id, batch_size, elapsed_ms, timeout 여부

## DoD (Definition of Done)
- toy가 아닌 **실제 임베딩 모델**이 `/v1/embed`에 연결됨
- `normalize=true/false`가 동작하고 dim/모델명이 정확히 반환됨
- 최소 스모크 테스트/유사도 sanity pass
- contract test 및 lint/test 통과
- 문서: `docs/mis/embed.md` 추가(설정/예시 curl)

## Files (expected)
- `services/model-inference-service/app/core/models.py` (embed 모델 클래스 추가/선택 로직)
- `services/model-inference-service/app/api/routes.py` (embed handler 연결)
- `services/model-inference-service/app/core/settings.py` (env 추가)
- `contracts/mis-embed-*.schema.json` (+ examples)
- `docs/mis/embed.md`
- `services/model-inference-service/tests/test_embed.py` (신규/확장)

## Commands
- run MIS locally (예시)
  - `MIS_EMBED_BACKEND=onnx MIS_EMBED_MODEL_ID=bge-m3 uvicorn app.main:app --reload`
- smoke
  - `curl -X POST $MIS_URL/v1/embed -H 'Content-Type: application/json' -d '{"model":"bge-m3","normalize":true,"texts":["해리포터 1권","해리포터 마법사의 돌"]}'`

## Codex Prompt
- Implement real embedding model serving in MIS /v1/embed replacing toy behavior.
- Prefer ONNX Runtime backend; keep toy as fallback.
- Keep request/response schema compatible; update contracts/examples and add tests + docs.
