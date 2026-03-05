---
title: "08. Hybrid Retrieval + Fallback + 2-Pass 재검색"
slug: "bsl-backend-series-08-hybrid-retrieval-fallback"
series: "BSL Backend Technical Series"
episode: 8
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 08. Hybrid Retrieval + Fallback + 2-Pass 재검색

## 핵심 목표
Search Service는 “한 번 실패하면 끝”이 아니라, lexical/vector/rerank 실패를 단계별로 흡수해 응답을 끝까지 만들도록 설계했습니다.

핵심 구현:
- `services/search-service/.../HybridSearchService.java`
- `SearchQualityEvaluator.java`
- `query/QueryServiceGateway.java`
- `resilience/SearchResilienceRegistry.java`

## 1) 실행 흐름 (`searchWithQcV11`)
주요 순서는 아래와 같습니다.

1. QC v1.1 계약 확인
2. 실행 계획 생성
3. lexical + vector 병렬 retrieval
4. fuse 후 결과 품질 평가
5. 필요 시 Query Enhance 호출 후 2차 검색(1회)
6. rerank 적용
7. 실패 시 fallback으로 수렴

## 2) 품질 트리거
`SearchQualityEvaluator`가 enhance 필요 여부를 계산합니다.

대표 트리거:
- `ZERO_RESULTS`
- `LOW_RESULTS`

판정은 히트 수, 상위 score 임계치 기반으로 수행합니다.

## 3) Enhance 연동 skip 조건
Query Service enhance를 무조건 호출하지 않습니다.

대표 skip reason:
- `EXPLICIT_FIELD_ROUTING`
- `MISSING_QUERY_TEXT`
- `ISBN_QUERY`
- `BUDGET_EXHAUSTED`
- `EMPTY_ENHANCE_RESPONSE`
- `ENHANCE_SKIP`
- `EMPTY_FINAL_QUERY`

정확한 질의(명시 필드/ISBN)에서 rewrite를 억제해 품질 흔들림을 막습니다.

## 4) fallback 트리거(중요)
retrieval/rerank 오류는 fallback 정책으로 흡수합니다.

- `VECTOR_ERROR`
- `ZERO_RESULTS`
- `RERANK_ERROR`

fallback 적용은 계획(`when.onVectorError/onTimeout/onRerankError/onZeroResults`)에 따라 결정됩니다.

## 5) rerank skip 정책
rerank도 조건 충족 시에만 실행합니다.

- `rerank_disabled`
- `rerank_no_candidates`
- `rerank_topk_zero`
- `rerank_policy_disabled`
- `rerank_skipped_isbn`
- `rerank_skipped_short_query`
- `rerank_skipped_min_candidates`
- `rerank_budget_exhausted`

이를 통해 비용이 큰 단계의 무의미한 실행을 줄였습니다.

## 6) 회로 차단기
`SearchResilienceRegistry`의 circuit breaker가 vector/rerank 연쇄 실패를 차단합니다.

`application.yml`에서 임계값을 조정합니다.
- `SEARCH_VECTOR_FAIL_THRESHOLD`, `SEARCH_VECTOR_OPEN_MS`
- `SEARCH_RERANK_FAIL_THRESHOLD`, `SEARCH_RERANK_OPEN_MS`

## 로컬 점검
```bash
curl -sS http://localhost:8002/search \
  -H 'Content-Type: application/json' \
  -d '{"query_context": {...}, "debug": true}' | jq
```

`quality.reason`, `enhanceOutcome`, `fallback`, `rerank.reason`을 같이 확인하면 실패 흡수 경로가 보입니다.

## 7) 품질 평가 기본 임계값
`SearchQualityProperties` 기본값:

1. `lowResultsHitsThreshold=3`
2. `lowResultsTopScoreThreshold=0.02`

즉, hits가 적고 top score도 낮으면 `LOW_RESULTS`로 분류합니다.

## 8) `maybeRetryWithEnhance()` 세부 흐름
코드 기준으로 enhance 재검색은 아래 순서로 수행됩니다.

1. 품질 평가로 reason 확보
2. explicit field routing이면 즉시 skip
3. `qNorm` 확보 실패 시 skip
4. ISBN 질의면 skip
5. 잔여 budget 계산
6. Query Service `/query/enhance` 호출
7. `decision=RUN`이고 `finalQuery`가 유효하면 1회 재검색
8. 개선 여부(`improved`) 평가

핵심 skip code:
- `EXPLICIT_FIELD_ROUTING`
- `MISSING_QUERY_TEXT`
- `ISBN_QUERY`
- `BUDGET_EXHAUSTED`
- `QS_TIMEOUT_OR_ERROR`
- `EMPTY_ENHANCE_RESPONSE`
- `ENHANCE_SKIP`
- `EMPTY_FINAL_QUERY`

## 9) fallback policy 매칭 규칙
`applyFallback()`는 정책의 `when` 조건과 trigger를 매칭합니다.

1. `VECTOR_ERROR -> onVectorError | onTimeout`
2. `RERANK_ERROR -> onRerankError | onRerankTimeout`
3. `ZERO_RESULTS -> onZeroResults`

조건이 맞으면 mutation(`disable vector/rerank`, query source 전환, topK 조정)을 적용한 새 실행계획을 생성합니다.

## 10) 설정에서 중요한 예산/복원력 파라미터
`application.yml` 주요 값:

1. budget split: lexical 0.5 / vector 0.3 / rerank 0.2
2. min stage ms: 20
3. resilience breaker:
   - vector fail threshold 3, open 30000ms
   - rerank fail threshold 3, open 30000ms
4. rerank 정책:
   - max top-k 50
   - min candidates 5
   - min query length 2
   - skip isbn true

## 11) 로컬 디버깅 시 체크 순서
1. quality reason (`ZERO_RESULTS`/`LOW_RESULTS`)
2. enhance outcome(시도/skip 이유)
3. fallback policy id
4. rerank reason code
5. 최종 전략 문자열(`hybrid_rrf_v1_1` 등)

이 순서로 보면 “왜 결과가 그렇게 나왔는지”를 빠르게 추적할 수 있습니다.
