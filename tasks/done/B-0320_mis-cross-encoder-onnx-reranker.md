# B-0320 — MIS: Cross-Encoder ONNX reranker (real model) + routing

## Goal
MIS의 `/v1/score`가 toy 또는 ONNX rerank 모델을 지원하지만,
실제로 “cross-encoder reranker”가 제품 수준으로 구성되지 않았다.
Cross-encoder 기반 rerank를 ONNX로 서빙하고,
Ranking Service가 이를 안정적으로 호출하도록 만든다.

## Why
- Hybrid 후보(topN)를 정밀 재정렬하는 마지막 품질 회수 단계.
- LTR(cheap) + cross-encoder(expensive) 2-stage의 “expensive” 파트 완성.

## Scope
### In-scope
1) cross-encoder ONNX 모델 로딩/서빙
- model id로 로드
- warmup
- batch scoring 지원
- max_len / truncation / tokenization 고정

2) `/v1/score` 요청 스키마 확정(이미 있다면 강화)
- query + docs(text fields) 또는 query + features + doc_text
- 최소 요구 텍스트 필드 정의(제목/저자/요약/베스트 chunk)

3) 성능 가드레일
- topR 상한(예: 50)
- timeout budget
- overload 시 429/503 + reason

### Out-of-scope
- LTR LambdaMART ONNX(Phase 6)
- GPU 최적화 심화

## DoD
- ONNX cross-encoder 모델이 실제로 load되어 점수 반환
- toy 대비 랭킹이 달라짐(스모크)
- timeout/overload 시 graceful 실패
- contracts/examples/tests/docs 업데이트

## Files (expected)
- `services/model-inference-service/app/core/models.py`
- `services/model-inference-service/app/api/routes.py`
- `services/model-inference-service/app/core/settings.py`
- `contracts/mis-score-*.schema.json` (+ examples)
- `docs/mis/rerank.md`
- tests

## Codex Prompt
- Add production-grade cross-encoder rerank model support in MIS /v1/score using ONNX Runtime.
- Provide robust batching/timeout/guardrails and update contracts/tests/docs.
