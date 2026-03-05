---
title: "21. Search Fusion 정책: RRF/Weighted 전환과 예산 분할"
slug: "bsl-backend-series-21-search-fusion-policy-budget"
series: "BSL Backend Technical Series"
episode: 21
status: "draft"
date: "2026-03-03"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 21. Search Fusion 정책: RRF/Weighted 전환과 예산 분할

## 핵심 목표
Search Service의 하이브리드 점수 병합이 고정 수식이 아니라, 실험 가능한 정책 계층이라는 점을 코드 기준으로 정리합니다.

핵심 구현 파일:
- `services/search-service/src/main/java/com/bsl/search/merge/RrfFusion.java`
- `services/search-service/src/main/java/com/bsl/search/merge/WeightedFusion.java`
- `services/search-service/src/main/java/com/bsl/search/service/HybridSearchService.java`
- `services/search-service/src/main/java/com/bsl/search/retrieval/FusionPolicyProperties.java`
- `services/search-service/src/main/java/com/bsl/search/service/SearchBudgetProperties.java`

## 1) RRF 수식
`RrfFusion.fuse()`는 문서별 점수를 아래처럼 누적합니다.

- lexical 기여: `1 / (k + lex_rank)`
- vector 기여: `1 / (k + vec_rank)`
- 최종: 두 값을 합산

`k`가 클수록 상위 rank 편향이 완화됩니다.

## 2) Weighted 수식
`WeightedFusion.fuse()`는 동일한 랭크 기반 수식에 가중치를 곱합니다.

- lexical: `lexWeight * 1/(k+rank)`
- vector: `vecWeight * 1/(k+rank)`

따라서 score 스케일은 랭크 구조를 유지하면서 소스별 영향도만 조정됩니다.

## 3) 동점 처리 규칙
두 구현 모두 정렬 기준은 동일합니다.

1. score 내림차순
2. docId 오름차순

그리고 `fusedRank = i+1`를 다시 기록해 후속 단계(rerank features)에서 사용합니다.

## 4) fusion 방식 결정 순서
`resolveFusionMethod()` 우선순위:

1. QC 힌트의 method (`plan.fusionMethod`)가 있으면 우선
2. 실험 모드(`experimentEnabled`)가 켜져 있으면 requestId hash 샘플링
3. 그 외에는 `defaultMethod`
4. 어떤 값도 없으면 `RRF`

## 5) 실험 샘플링 방식
`hashToUnitInterval(requestId)`로 `0~1` 값을 만든 뒤,
`weightedRate`보다 작으면 Weighted를 선택합니다.

즉, requestId 기반 고정 샘플링이라 동일 requestId는 동일 정책을 재현할 수 있습니다.

## 6) budget 분할 알고리즘
`applyBudgetSplit()`는 `timeBudgetMs`를 lexical/vector/rerank로 분해합니다.

기본 share:
- lexical 0.5
- vector 0.3
- rerank 0.2

세 share는 합이 1이 아니어도 정규화합니다.

## 7) 최소 스테이지 보장
`SearchBudgetProperties.minStageMs`(기본 20ms)를 하한으로 두고 `clampBudget()`를 적용합니다.

벡터/리랭크가 비활성화된 경우에는 해당 stage budget을 0으로 둡니다.

## 8) budget 미설정 폴백
`search.budget.enabled=false`거나 설정이 없으면,
lexical/vector/rerank 모두 전체 budget을 그대로 사용합니다.

실험 초기에는 이 모드가 디버깅에 유리합니다.

## 9) QC 힌트와의 결합
`buildPlanFromQcV11()`에서 QC의 `executionHint.budgetMs`가 있으면 stage budget을 먼저 넣고,
이후 `applyBudgetSplit()`가 비어 있는 값만 채웁니다.

즉, QC가 명시한 budget이 최우선입니다.

## 10) strategy 문자열 반영
`applyFusionSuffix()`는 weighted 사용 시 `hybrid_rrf_*` 문자열의 `rrf`를 `weighted`로 치환합니다.

예시:
- `hybrid_rrf_v1_1` -> `hybrid_weighted_v1_1`

응답 strategy만 봐도 어떤 융합 정책이 적용됐는지 파악할 수 있습니다.

## 11) debug에서 확인할 수 있는 정보
`buildDebug()`를 켜면 아래를 확인할 수 있습니다.

- lexical/vector query DSL
- 각 stage topK, tookMs, error/timedOut
- fusion tookMs
- warning 목록(`vector_timeout`, `rerank_error` 등)

## 12) 로컬 검증 시나리오
```bash
curl -sS http://localhost:8002/search \
  -H 'Content-Type: application/json' \
  -d '{"query_context_v1_1": {...}, "options": {"debug": true, "timeoutMs": 220}}' | jq
```

점검 포인트:
1. `strategy`에 weighted 반영 여부
2. `debug.retrieval.fusion.tookMs`
3. `debug.retrieval.lexical/vector/rerank.topK`

## 13) 구현상 주의점
weight를 크게 조정해도 랭크 기반 수식 특성상 절대 점수보다는 순위 변화가 핵심입니다.

따라서 실험은 "점수 평균"보다 `topN 순위 변동 + 클릭 로그`로 평가해야 의미가 있습니다.
