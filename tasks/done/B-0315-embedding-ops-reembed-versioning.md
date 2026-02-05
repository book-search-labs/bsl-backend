# B-0315 — Offline Eval: Vector/Hybrid 회귀 테스트 (Toy vs Real 비교)

## Goal
Vector embedding 개선이 실제로 품질을 올렸는지 정량 검증한다.  
Toy baseline과 real embedding 후보를 비교하는 **offline eval 스크립트**를 만들고, 리포트를 산출한다.

## Why
- embedding 변경은 품질을 망칠 수도 있다(도메인 mismatch, 텍스트 구성 문제 등).
- 최소한 Recall/NDCG가 baseline보다 좋아졌는지 자동으로 확인해야 운영이 가능하다.

## Scope
1) 평가 쿼리셋 구성
- Golden(고정): 200~1000개(수동/반수동 라벨 가능)
- Hard set: 오타/초성/권차/시리즈/유사어 질의
- (선택) Shadow: 최근 인기 질의(로그 기반)

2) 평가 모드
- vector-only(topK)
- hybrid(BM25 + vector + RRF) (가능하면)

3) 지표
- Recall@50 (retrieval 품질)
- NDCG@10, MRR@10 (랭킹 민감)
- 0-result-rate
- latency proxy(옵션: 단계별 호출수/예산)

4) 리포트 산출
- JSON + markdown 요약
- baseline vs candidate diff 포함

## Non-goals
- LTR 학습/배포 게이트는 Phase 6 티켓(B-0295/I-0318)에서 다룸
- 온라인 A/B 실험은 별도

## Interfaces / Contracts
입력(권장):
- `data/eval/queries.jsonl`:
  - `{ "qid":"...", "query":"...", "relevant_doc_ids":["..."] }`

출력:
- `data/eval/reports/vector_eval_<ts>.json`
- `data/eval/reports/vector_eval_<ts>.md`

## Design Notes
- 초기에는 라벨이 부족할 수 있으므로 'relevant_doc_ids'를 최소 1개라도 확보하는 방식으로 시작한다.
- hybrid 평가를 하려면 Search Service의 내부 API를 호출하거나, OS 쿼리를 직접 수행해도 된다(간단하게 시작).

## DoD (Definition of Done)
- `python scripts/eval/vector_eval.py --baseline toy --candidate embed_v1` 실행 가능
- 리포트가 baseline 대비 개선/퇴보를 보여줌(샘플 리포트 포함)
- 최소 20개 '개선 사례/실패 사례'를 로그로 남겨 원인 분석 가능

## Files / Modules
- (신규) `scripts/eval/vector_eval.py`
- `data/eval/queries.jsonl` (샘플 포함)
- (선택) `scripts/eval/README.md`

## Commands (examples)
```bash
python scripts/eval/vector_eval.py --baseline toy --candidate embed_ko_v1 --topk 50 --out data/eval/reports
```

## Codex Prompt (copy/paste)
```text
Implement B-0315:
- Create scripts/eval/vector_eval.py that evaluates vector-only and (optionally) hybrid retrieval.
- Input: data/eval/queries.jsonl containing qid, query, relevant_doc_ids.
- Metrics: Recall@50, NDCG@10, MRR@10, 0-result-rate; output JSON and markdown report with baseline vs candidate diffs.
- Include a small sample queries.jsonl and a sample report.
```
