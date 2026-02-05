# B-0323 — Rerank: offline eval + CI gate (quality regression prevention)

## Goal
Rerank(Heuristic/Toy/ONNX)이 바뀌어도 품질이 떨어지면 배포를 막아야 한다.
오프라인 평가 러너를 만들고 CI에서 기준 대비 하락 시 실패하도록 한다.

## Why
- “좋아졌겠지” 배포는 운영 리스크가 큼.
- LTR(Phase 6)로 가기 전에 rerank부터 회귀 게이트 패턴을 확립하면 전체 품질 문화가 생김.

## Scope
### In-scope
1) rerank 평가 데이터셋
- Golden set(고정)
- Hard set(오타/권차/시리즈/혼용)
- 최소 100~500 쿼리로 시작

2) rerank eval runner
- 입력: query + candidate docs(또는 재현 가능한 retrieval seed)
- 비교:
  - baseline(현재) vs candidate(새 모델/정책)
- 지표:
  - NDCG@10, MRR@10, Recall@100, 0-result-rate
  - rerank latency proxy, rerank_call_rate

3) CI gate
- 기준 대비 NDCG 하락, 0-result-rate 상승 등 threshold 설정
- 실패 시 리포트 첨부(artifact)

### Out-of-scope
- 대규모 라벨링 UI(A-0123) — 향후 확장

## DoD
- 로컬에서 `make eval-rerank` 같은 단일 커맨드로 리포트 생성
- CI에서 eval 단계가 돌아가고, threshold 위반 시 fail
- docs에 운영 방법 기록

## Files (expected)
- `scripts/eval/rerank_eval.py` (신규)
- `data/eval/rerank_queries.jsonl`
- `.github/workflows/*` 또는 CI 스크립트
- `docs/eval/rerank_eval.md`

## Codex Prompt
- Add rerank offline evaluation runner and wire it into CI as a regression gate.
- Provide dataset samples, thresholds, and clear docs.
