---
title: "23. Material Grouping: 판본/세트 페널티와 대표본 선택"
slug: "bsl-backend-series-23-material-grouping-penalty-selection"
series: "BSL Backend Technical Series"
episode: 23
status: "draft"
date: "2026-03-03"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 23. Material Grouping: 판본/세트 페널티와 대표본 선택

## 핵심 목표
Search 결과에서 같은 작품이 여러 판본으로 중복될 때, 어떤 기준으로 대표본을 고르고 변형본을 보충하는지 정리합니다.

핵심 구현 파일:
- `services/search-service/src/main/java/com/bsl/search/service/grouping/MaterialGroupingService.java`
- `services/search-service/src/main/java/com/bsl/search/service/grouping/MaterialGroupingProperties.java`

## 1) 적용 시점
`HybridSearchService`는 retrieval/rerank가 끝난 뒤 마지막에 `groupingService.apply()`를 호출합니다.

즉, 그룹핑은 검색기 점수 계산을 바꾸지 않고, 최종 노출 목록만 재정렬합니다.

## 2) 그룹 키 생성 규칙
`groupKey()`는 아래를 합쳐 키를 만듭니다.

- 정규화 title
- 첫 author
- volume

정규화된 title이 핵심입니다. `normalizeTitle()`이 strip token과 영숫자 필터를 적용해 판본 문구를 제거합니다.

## 3) 기본 strip token
설정이 없으면 아래 토큰을 제목에서 제거합니다.

- `recover`, `reprint`, `special`, `limited`, `set`, `box`, `bundle`, `revised`

덕분에 "일반판 vs 리커버판"이 같은 그룹으로 묶일 가능성이 높아집니다.

## 4) 그룹 내부 대표본 선택
각 그룹에서 `pickBest()`가 대표본 1개를 선택합니다.

정렬 기준:
1. `adjustedScore` 최대
2. 동점이면 더 앞에 나온 항목 우선(원 순위 보존)

## 5) adjustedScore 페널티
`adjustedScore()`는 원점수에서 판본별 페널티를 뺍니다.

- recover/reprint: `recoverPenalty`
- set/box/bundle: `setPenalty` (단, 질의가 세트를 선호하면 면제)
- special/limited/anniversary: `specialPenalty`

## 6) 질의의 세트 선호 감지
`queryPrefersSet`가 true면 set 페널티를 적용하지 않습니다.

즉, 사용자가 "세트"를 명시한 질의에서는 박스세트가 부당하게 밀리지 않도록 처리합니다.

## 7) overflow fill 전략
대표본만 모으면 개수가 부족할 수 있습니다.

`fillVariants=true`이면
1. 대표본을 먼저 채우고
2. 남은 슬롯은 overflow(비대표본)를 원 순서대로 보충합니다.

결과 리스트 길이를 유지하면서 중복 노출만 완화합니다.

## 8) 기본 프로퍼티
`MaterialGroupingProperties` 기본값:

- `enabled=false`
- `fillVariants=true`
- `recoverPenalty=0.15`
- `setPenalty=0.2`
- `specialPenalty=0.1`

토큰 리스트(`titleStripTokens`, `recoverTokens`, `setTokens`, `specialTokens`)는 비어 있으면 코드 기본 목록을 사용합니다.

## 9) 랭크 재계산
그룹핑 후 최종 리스트를 다시 순회하면서 `rank=i+1`로 재부여합니다.

따라서 API 응답의 rank는 그룹핑 이후 순서 기준입니다.

## 10) 적용 시 주의점
그룹 키가 title/author/volume 기반이라, 저자명이 누락된 메타데이터에서는 과그룹핑/미그룹핑이 생길 수 있습니다.

이 경우 우선순위는:
1. author 품질 개선
2. strip token 튜닝
3. penalty 값 튜닝

## 11) 로컬 검증
```bash
curl -sS http://localhost:8002/search \
  -H 'Content-Type: application/json' \
  -d '{"query_context_v1_1": {...}, "options": {"size": 20, "debug": true}}' | jq
```

검증 포인트:
1. 같은 작품군의 중복 hit 수 감소
2. 세트 질의에서 set 페널티 면제 여부
3. `size`를 키웠을 때 overflow 변형본 보충 여부

## 12) 구현 의도
이 로직의 목적은 정답률을 바꾸는 것이 아니라, "SERP 해석 난이도"를 낮추는 것입니다.

같은 작품의 변형이 첫 화면을 점유하면 사용자는 탐색 비용이 급격히 증가합니다. 그룹핑은 이 비용을 줄이기 위한 마지막 정렬 계층입니다.
