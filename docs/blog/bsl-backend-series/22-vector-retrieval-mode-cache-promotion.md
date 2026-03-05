---
title: "22. Vector Retrieval 모드 매트릭스: 임베딩, 캐시, Doc 승격"
slug: "bsl-backend-series-22-vector-retrieval-mode-cache-promotion"
series: "BSL Backend Technical Series"
episode: 22
status: "draft"
date: "2026-03-03"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 22. Vector Retrieval 모드 매트릭스: 임베딩, 캐시, Doc 승격

## 핵심 목표
Vector retrieval 경로가 하나가 아니라 `mode`별로 달라지고, 캐시/회로차단기/문서 승격이 함께 동작하는 구조를 정리합니다.

핵심 구현 파일:
- `services/search-service/src/main/java/com/bsl/search/retrieval/VectorRetriever.java`
- `services/search-service/src/main/java/com/bsl/search/retrieval/VectorSearchProperties.java`
- `services/search-service/src/main/java/com/bsl/search/retrieval/VectorResultCacheService.java`
- `services/search-service/src/main/java/com/bsl/search/retrieval/VectorDocPromoter.java`
- `services/search-service/src/main/java/com/bsl/search/embed/EmbeddingService.java`

## 1) 모드별 실행 경로
`VectorSearchMode`에 따라 분기됩니다.

1. `DISABLED`: 즉시 skip (`vector_disabled`)
2. `OPENSEARCH_NEURAL`: text 직접 neural 검색 (`modelId` 필수)
3. `CHUNK`: query embedding 생성 후 chunk kNN
4. `EMBEDDING`(기본): query embedding 생성 후 doc kNN

## 2) OPENSEARCH_NEURAL 제약
`OPENSEARCH_NEURAL`에서는 `modelId`가 비어 있으면 에러를 반환합니다.

이 경로는 embedding provider를 거치지 않으므로, 모델 관리 지점을 OpenSearch 쪽으로 옮긴 구성입니다.

## 3) EMBEDDING/CHUNK 공통점
두 모드는 `EmbeddingProvider.embed()`를 먼저 호출합니다.

그다음:
- EMBEDDING: `searchVectorDetailed()`
- CHUNK: `searchChunkVectorDetailed()`

즉, 인덱스 타입만 다르고 query vector 생성 경로는 동일합니다.

## 4) Vector 결과 캐시 키 구성
`VectorResultCacheService.buildKey()`는 JSON hash 기반 키를 만듭니다.

키 필드:
- 정규화된 query
- `top_k`
- `filters`
- `mode`
- `model`

결과 key는 `vec:<hash>` 형식입니다.

## 5) 캐시 스킵 조건(중요)
아래 조건이면 캐시를 사용하지 않습니다.

1. cache 비활성
2. query 비어 있음
3. query 길이 제한 초과(`maxTextLength`)
4. debug/explain 요청이고 `cacheDebug=false`

디버그 관측 시 캐시 오염을 줄이기 위한 의도입니다.

## 6) 캐시 기본값
`VectorSearchProperties.Cache` 기본값:

- `enabled=false`
- `ttlMs=20000`
- `maxEntries=2000`
- `maxTextLength=200`
- `normalize=true`
- `cacheDebug=false`

## 7) Doc 승격(`VectorDocPromoter`)
벡터 결과가 chunk docId일 때 base doc으로 승격해 중복을 줄입니다.

기본 separator:
- `#,::`

동작:
1. separator 기준 prefix 추출
2. `LinkedHashSet`으로 dedup
3. 최초 순서 보존

## 8) 승격이 필요한 이유
chunk 검색은 같은 도서의 여러 chunk가 상위에 몰릴 수 있습니다.

승격으로 문서 단위 다양성을 확보한 뒤, 이후 fusion/rerank에서 다시 순위를 조정합니다.

## 9) EmbeddingService의 회로 차단기
`EmbeddingService.fetch()`는 HTTP 모드에서 `embedBreaker`를 사용합니다.

- breaker open -> `embed_circuit_open`
- 성공 -> `recordSuccess()`
- 실패 -> `recordFailure()`

그래서 embedding 장애가 vector 단계 전체 장애로 연쇄되는 것을 억제합니다.

## 10) 임베딩 캐시 계층
`EmbeddingService`는 별도 `EmbeddingCacheService`를 통해
`get -> fetchAndCache -> put` 패턴을 수행합니다.

query embedding이 반복되는 핫쿼리에서 가장 먼저 비용 절감이 발생합니다.

## 11) SearchService와 결합되는 지점
`HybridSearchService.retrieveCandidates()`는 vector stage 결과를 받아

- rank map 생성
- fusion
- source mget
- debug/warnings 생성

순서로 연결합니다. vector 단계가 실패해도 lexical 결과로 전체 응답은 유지됩니다.

## 12) 로컬 검증
```bash
curl -sS http://localhost:8002/search \
  -H 'Content-Type: application/json' \
  -d '{"query_context_v1_1": {...}, "options": {"debug": true}}' | jq
```

확인 포인트:
1. `debug.retrieval.vector.error/timedOut`
2. `debug.warnings`의 `vector_skipped|vector_timeout|vector_error`
3. 동일 질의 반복 시 vector tookMs 감소(캐시 활성 시)

## 13) 튜닝 우선순위
로컬 테스트 기준으로는 아래 순서가 효과가 컸습니다.

1. `mode` 선택(EMBEDDING vs CHUNK)
2. query embedding 캐시 on/off
3. doc promotion on/off
4. `topK`와 rerank budget 조정

결국 vector 품질은 단일 모델보다 "모드 + 예산 + 후처리" 조합의 영향이 더 큽니다.
