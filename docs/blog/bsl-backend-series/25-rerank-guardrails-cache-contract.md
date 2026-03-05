---
title: "25. Rerank Guardrail/Cache 계약: 상한선과 이유코드"
slug: "bsl-backend-series-25-rerank-guardrails-cache-contract"
series: "BSL Backend Technical Series"
episode: 25
status: "draft"
date: "2026-03-03"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 25. Rerank Guardrail/Cache 계약: 상한선과 이유코드

## 핵심 목표
리랭크 품질보다 먼저 지켜야 하는 것은 입력 상한과 실패 계약입니다. 실제 코드의 guardrail/캐시 정책을 정리합니다.

핵심 구현 파일:
- `services/ranking-service/src/main/java/com/bsl/ranking/service/RerankGuardrailsProperties.java`
- `services/ranking-service/src/main/java/com/bsl/ranking/service/RerankCacheProperties.java`
- `services/ranking-service/src/main/java/com/bsl/ranking/service/RerankScoreCache.java`
- `services/ranking-service/src/main/java/com/bsl/ranking/service/RerankService.java`

## 1) guardrail 기본값
`RerankGuardrailsProperties` 기본값:

- `maxCandidates=200`
- `maxTopN=50`
- `maxMisCandidates=100`
- `minCandidatesForMis=5`
- `minQueryLengthForMis=2`
- `timeoutMsMax=500`

## 2) size/timeout 상한 적용
`resolveSize()`와 `resolveTimeoutMs()`에서 상한을 적용하며 reason code를 남깁니다.

- `size_capped`
- `timeout_capped`

요청값이 공격적으로 들어와도 서비스 내부 제한을 넘지 않습니다.

## 3) candidate 상한 적용
`applyCandidateLimit()`은 입력 후보가 많으면 `maxCandidates`까지 자릅니다.

이때 `candidates_capped` reason code가 추가됩니다.

## 4) MIS 입력 상한
`applyMisLimit()`은 MIS 호출 후보를 `maxMisCandidates`로 추가 제한합니다.

즉, 전체 후보 200건을 받아도 MIS 호출은 100건으로 제한될 수 있습니다.

## 5) score cache 키 구조
MIS score cache key:

`rerank:{model}:{query_hash}:{doc_id}`

`query_hash`는 소문자/공백 정규화 후 SHA-256으로 생성됩니다.

## 6) cache 기본값
`RerankCacheProperties` 기본값:

- `enabled=true`
- `ttlSeconds=900`
- `maxEntries=10000`

동일 query/doc/model 조합의 반복 요청에서 MIS 호출 횟수를 크게 줄입니다.

## 7) cache eviction 정책
`RerankScoreCache.evictIfNeeded()`는 2단계로 동작합니다.

1. 만료 엔트리 우선 제거
2. 여전히 초과면 순회 제거

LRU는 아니지만 구현 복잡도를 낮추고, TTL 기반 신선도를 우선시한 전략입니다.

## 8) cache 장애 격리
`safeCacheGet/Put()`는 예외를 삼키고 진행합니다.

즉, cache 레이어 장애가 rerank 전체 실패로 전파되지 않습니다.

## 9) stage skip 코드 체계
`StageResult.skipped()`를 통해 skip 사유를 코드화합니다.

대표 코드:
- `skip_disabled`
- `skip_no_candidates`
- `skip_topk_zero`
- `skip_not_eligible`

운영이 아니라 로컬 분석에서도 원인 재현이 쉬워집니다.

## 10) stage degrade 코드
stage2 MIS 실패 시 아래 코드로 degrade됩니다.

- timeout: `timeout_degrade_to_stage1`
- 기타 오류: `error_degrade_to_stage1`

응답은 계속 반환하고, reason code로 품질 저하만 표시합니다.

## 11) MIS 계약 실패 방어
`scoreWithMis()`는 아래를 강제합니다.

1. 응답 body 존재
2. `scores` 배열 존재
3. `scores.size == 요청 candidate 수`

한 항목이라도 어긋나면 `MisUnavailableException`으로 처리해 즉시 degrade합니다.

## 12) 로컬 검증 체크리스트
1. 후보 300건으로 호출해 `candidates_capped` 확인
2. timeout 2000ms 요청으로 `timeout_capped` 확인
3. MIS 비활성화 상태에서 `skip_not_eligible`/heuristic 모델 확인
4. 동일 질의 반복으로 cache hit metric 증가 확인

## 13) 왜 이 구조가 중요한가
리랭크는 품질을 높여도, 상한이 없으면 레이턴시와 비용이 폭증합니다.

이 구현은 "최대 성능"보다 "예측 가능한 성능"을 우선해, 실험 중에도 시스템 전체를 보호하도록 구성되어 있습니다.
