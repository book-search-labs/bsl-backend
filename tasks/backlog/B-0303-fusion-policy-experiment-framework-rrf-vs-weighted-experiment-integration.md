# B-0303 — Fusion 정책 실험 프레임(RRF vs Weighted) + 실험 연결

## Goal
Hybrid 검색에서 **Fusion(RRF/Weighted/룰 기반)** 정책을 “코드 수정 없이” 바꿀 수 있게 하고,
**실험(Experiment/FeatureFlag)** 으로 트래픽을 나눠 **온라인/오프라인 평가**까지 연결한다.

## Why
- RRF가 기본값으로 좋지만, 도메인/트래픽에 따라 Weighted(가중합)나 규칙 기반이 더 나을 수 있음
- Fusion은 품질에 큰 영향인데, 매번 배포로 바꾸면 느리고 위험함 → 실험 프레임이 필요

## Scope
### 1) Fusion Strategy 인터페이스/플러그인 구조 (SR 내부)
- `FusionStrategy`:
  - input: `bm25_ranked_docs`, `vector_ranked_docs` (+ optional scores)
  - output: `fused_ranked_docs` + debug breakdown
- 구현체:
  - `RrfFusionStrategy`
  - `WeightedFusionStrategy` (weights, score_norm 정책 포함)
  - `RuleFusionStrategy` (ex: ISBN/정확일치 우선)

### 2) Fusion Config (정책/실험 값)
- `search_policy`(또는 `ranking_policy`) 테이블에:
  - `fusion_mode` (RRF/WEIGHTED/RULE)
  - `fusion_params_json` (rrf_k, weights, score_norm, caps)
- BFF에서 policy를 내려주거나 SR에서 policy 조회(둘 중 1)

### 3) Experiment 연결
- request 단위로 experiment bucket 결정:
  - `exp_fusion_mode`: control(RRF) vs variant(WEIGHTED)
- 이벤트 로깅에 experiment 정보 포함(B-0232)

### 4) Evaluation 연동
- Offline eval(B-0295)에서 **pipeline_config**로 fusion 전략별 점수 비교 가능해야 함
- “실험 결과 리포트”가 `eval_run`과 매핑되도록 config 기록

## Non-goals
- 완전한 실험 플랫폼 구축(초기엔 bucket hash 기반만으로 시작 가능)
- 다변량 최적화 자동화(추후)

## DoD
- SR에서 fusion 전략을 config로 스위치 가능
- debug=true 시 fusion breakdown이 노출됨(랭크/점수/가중치)
- 동일 query set을 fusion별로 offline eval 돌려 비교 가능
- search_impression 이벤트에 experiment/policy가 포함됨

## Codex Prompt
Implement fusion experiment framework:
- Create FusionStrategy interface and implement RRF and Weighted fusion with configurable params.
- Add policy/experiment config fields for fusion_mode and params.
- Include fusion breakdown in debug responses and persist experiment identifiers in search events.
- Ensure offline eval runner can run multiple fusion configs and compare results.
