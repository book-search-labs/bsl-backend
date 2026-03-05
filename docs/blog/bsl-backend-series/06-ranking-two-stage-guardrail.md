---
title: "06. Ranking 2-Stage + Guardrail 파이프라인"
slug: "bsl-backend-series-06-ranking-two-stage-guardrail"
series: "BSL Backend Technical Series"
episode: 6
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 06. Ranking 2-Stage + Guardrail 파이프라인

## 문제
rerank 품질을 올리고 싶다고 모든 후보를 고비용 모델에 넣으면 latency가 무너집니다. 반대로 너무 보수적이면 품질이 떨어집니다.

## 1) 입력 가드레일(중요)
`RerankService`는 시작점에서 요청을 캡합니다.

- 후보 수 상한: `maxCandidates`
- 응답 크기 상한: `maxTopN`
- timeout 상한: `timeoutMsMax`

상한 적용 시 reason code를 남깁니다.
- `candidates_capped`
- `size_capped`
- `timeout_capped`

“왜 결과가 줄었는지”를 코드로 설명할 수 있게 한 부분입니다.

## 2) 2-Stage 계획
`resolveStagePlan()`이 stage1/stage2를 나눕니다.

- Stage1: 기본 topK 50, 예산 약 40%
- Stage2: 남은 예산 약 60%
- 요청 옵션으로 stage별 `enabled/topK/model` override 가능

stage2 실패 시 stage1 결과로 degrade합니다.

- timeout: `timeout_degrade_to_stage1`
- error: `error_degrade_to_stage1`

## 3) stage skip 조건
상황에 따라 stage를 건너뜁니다.

- `skip_disabled`
- `skip_no_candidates`
- `skip_topk_zero`
- `skip_not_eligible`

불필요한 호출을 줄이면서도, skip 근거를 reason code로 추적 가능합니다.

## 4) MIS 호출과 캐시
rerank score 캐시 키는 모델/질의/문서를 포함합니다.

- key 패턴: `rerank:{model}:{queryHash}:{docId}`

관측 지표:
- `rs_rerank_cache_hit_total`
- `rs_rerank_cache_miss_total`
- `rs_mis_calls_total`

캐시가 잘 동작하면 stage2 품질을 유지하면서도 모델 호출 비용을 크게 줄일 수 있습니다.

## 5) 피처 스펙 고정
`FeatureSpecService`, `FeatureFetcher`로 입력 피처를 명시 관리합니다.

이 방식 덕분에 모델이 바뀌어도 “어떤 피처를 넣었는지”가 계약처럼 남습니다.

## 로컬 점검
```bash
# ranking 서비스 요청 시 debug 필드를 켜서 stage/reasonCodes 확인
curl -sS http://localhost:8082/rerank -H 'Content-Type: application/json' -d '{...}' | jq
```

핵심 확인값은 `reasonCodes`, `stage 결과`, `cache hit/miss`입니다.

## 6) Guardrail 기본값(코드 기준)
`RerankGuardrailsProperties` 기본값은 다음과 같습니다.

1. `maxCandidates=200`
2. `maxTopN=50`
3. `maxMisCandidates=100`
4. `minCandidatesForMis=5`
5. `minQueryLengthForMis=2`
6. `timeoutMsMax=500`

입력이 이 범위를 넘으면 reason code를 남기고 조정합니다.

## 7) MIS eligibility 판정 상세
MIS 호출은 아래 조건이 모두 충족될 때만 수행됩니다.

1. MIS enabled
2. timeout > 0
3. 후보 수 >= `minCandidatesForMis`
4. query 길이 >= `minQueryLengthForMis`

조건 미충족이면 stage2가 `skip_not_eligible`로 끝납니다.

## 8) Stage 2 degrade 동작
stage2 MIS 실패 시 즉시 실패하지 않고 stage1 결과로 degrade합니다.

1. timeout 계열: `timeout_degrade_to_stage1`
2. 기타 오류: `error_degrade_to_stage1`

즉, rerank 고도화 실패가 전체 검색 실패로 전파되지 않습니다.

## 9) 점수 캐시 구현 디테일
`RerankScoreCache`는 in-memory `ConcurrentHashMap` 기반이며 아래 정책을 따릅니다.

1. TTL 만료 시 get에서 제거
2. max entry 초과 시 만료 항목 우선 정리
3. 여전히 초과하면 순차 제거

기본 캐시 설정:
- enabled: `true`
- `ttlSeconds=900`
- `maxEntries=10000`

## 10) 디버그 관점에서 반드시 볼 필드
rerank debug를 볼 때는 아래를 같이 확인합니다.

1. `reasonCodes` (capped/skip/degrade)
2. stage별 in/out/topK/timeout/model
3. cache hit/miss 수
4. replay payload
5. feature set version

이 필드를 보면 품질 문제와 비용 문제를 분리해서 판단할 수 있습니다.
