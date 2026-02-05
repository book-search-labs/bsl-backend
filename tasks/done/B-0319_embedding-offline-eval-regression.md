# B-0319 — Embedding: offline eval + regression suite (vector quality gate foundation)

## Goal
임베딩 품질을 “감”으로 판단하지 않고,
오프라인 평가를 통해 **개선/퇴화**를 측정할 수 있는 최소 평가 스위트를 만든다.

## Why
- 임베딩 모델 교체 시 품질이 좋아졌는지/나빠졌는지 객관적으로 판단해야 함.
- 이후 LTR/Offline eval gate로 확장하기 위한 기반.

## Scope
### In-scope
1) 평가 데이터셋(최소)
- `data/eval/embedding_queries.jsonl` (쿼리 + 기대 관련 문서/키워드)
- Hard set: 오타/초성/권차/시리즈/영한 혼용 포함

2) 평가 스크립트
- 벡터 전용: OS kNN
- 하이브리드: BM25 + vector + RRF
- 지표:
  - Recall@K, MRR@K, NDCG@K, 0-result-rate
  - latency proxy(선택)

3) 리포트 산출
- JSON + Markdown 요약
- baseline(기존 모델) vs candidate(새 모델) 비교

### Out-of-scope
- CI gate 강제(I-0318/B-0295 범위)
- 대규모 라벨링 UI(A-0123 범위)

## DoD
- 1개 커맨드로 평가 리포트를 생성할 수 있음
- 최소 50개 쿼리로 실행 가능(작게 시작)
- 리포트가 git에 남고(샘플), 포맷이 안정적

## Files (expected)
- `scripts/eval/embedding_eval.py` (신규 or 기존 `scripts/eval/vector_eval.py` 확장)
- `data/eval/embedding_queries.jsonl`
- `data/eval/reports/*.json`, `*.md` (샘플)
- `docs/eval/embedding_eval.md`

## Commands
- `python scripts/eval/embedding_eval.py --mis-url http://localhost:9000 --os-url http://localhost:9200 --out data/eval/reports/run_001`

## Codex Prompt
- Implement offline embedding evaluation with hybrid option and standard metrics.
- Provide sample dataset + report outputs + docs.
