---
title: "03. Query Prepare: 정규화와 QueryContext v1.1 생성"
slug: "bsl-backend-series-03-query-prepare-querycontext-v11"
series: "BSL Backend Technical Series"
episode: 3
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 03. Query Prepare: 정규화와 QueryContext v1.1 생성

## 핵심 목표
검색 입력 문자열을 바로 OpenSearch에 던지지 않고, 먼저 Query Service에서 정규화/이해/힌트 생성을 끝낸 뒤 Search Service로 넘깁니다.

핵심 엔드포인트:
- `services/query-service/app/api/routes.py`: `POST /query/prepare`

## 1) prepare 파이프라인
`/query/prepare` 내부 흐름은 아래 순서입니다.

1. `_extract_ids`: trace/request 식별자 정리
2. `_prepare_analysis`: 정규화 + 질의 분석
3. `parse_understanding`: 명시 필터(author/title/isbn/series/publisher) 파싱
4. `_build_qc_v11_response`: QC v1.1 응답 조립

응답에는 이후 검색 계획에 필요한 `detected`, `reason`, `signals`, `retrievalHints` 계열 정보가 포함됩니다.

## 2) 정규화 디테일 (`app/core/normalize.py`)
정규화는 단순 trim이 아닙니다.

1. NFKC 정규화(icu 사용 가능 시 우선)
2. 제어문자 제거 + 공백 collapse
3. 문장부호/기호 통합
4. 권차/볼륨 표기 정규화 (`vol.2`, `제02권`, 로마 숫자)
5. 룰 기반 치환(`NORMALIZATION_RULES_PATH`)

빈 질의는 초기에 바로 차단합니다. 이 early-fail 덕분에 뒤 단계 조건식이 단순해집니다.

## 3) 질의 모드 감지 (`app/core/analyzer.py`)
분석기는 질의를 `isbn`, `chosung`, `mixed`, `normal` 등으로 분류합니다.

이 모드는 Search 단계에서 다음 분기에 직접 연결됩니다.
- ISBN 모드면 필드 라우팅/강한 exact 매칭
- 일반 모드면 lexical + vector 혼합

## 4) 이해도 파싱 (`app/core/understanding.py`)
`author:`, `title:`, `isbn:` 같은 명시 질의는 prepare 단계에서 구조화합니다.

중요 포인트:
- ISBN 필터는 논리 필드 `isbn13`으로 매핑
- 명시 필터가 있으면 후속 enhance를 skip할 근거가 된다(불필요한 rewrite 방지)

## 5) 캐시 키 버전 전략 (`app/api/routes.py`)
prepare 결과는 버전 포함 키로 캐시됩니다.

- `QS_NORM_CACHE_VERSION`
- `QS_NORM_CACHE_TTL_SEC`

알고리즘이 바뀌면 버전만 올려 캐시를 안전하게 무효화할 수 있습니다.

## 6) 왜 prepare를 서비스 경계로 뺐는가
검색 품질 문제를 분석할 때 책임 경계를 명확히 할 수 있기 때문입니다.

- Query Service: 입력 해석/정규화 실패
- Search Service: retrieval/fallback/rerank 실패

로컬 디버깅에서 이 분리는 체감상 가장 큰 생산성 개선이었습니다.

## 로컬 확인 명령
```bash
curl -sS http://localhost:8001/query/prepare \
  -H 'Content-Type: application/json' \
  -d '{"query":"해리포터 제2권"}' | jq
```

## 7) `_build_qc_v11_response`에서 실제로 조립되는 값
`routes.py` 기준으로 QC v1.1 응답은 아래 구조를 포함합니다.

1. `meta`: schemaVersion, trace/request/span, locale, tenant
2. `query`: raw/nfkc/norm/nospace/final/canonicalKey
3. `detected`: mode, isIsbn, hasVolume, lang, isMixed
4. `slots`: isbn, volume, edition, set, chosung
5. `understanding`: entities/constraints
6. `retrievalHints`: lexical/vector/rerank/filter 힌트
7. `debug.cache.norm_hit`

이 응답이 이후 Search Service의 실행 계획 입력이 됩니다.

## 8) `final` 질의 결정 규칙 (`_resolve_final_text`)
`query.final`은 아래 우선순위로 선택됩니다.

1. `residual_text`가 있으면 `explicit_residual`
2. 명시 필터가 있으면 entity 조합 결과(`explicit_entities`)
3. 그 외에는 `norm`

이 규칙으로 명시 질의(`author:`, `isbn:` 등)에서 불필요한 텍스트 손실을 줄입니다.

## 9) ISBN 명시 질의에서 retrieval 최적화
ISBN entity만 있고 residual text가 없으면 `retrievalHints`에서 아래를 끕니다.

1. `vector.enabled = false`
2. `rerank.enabled = false`

ISBN exact 매칭 상황에서는 고비용 단계를 건너뛰는 것이 더 안정적입니다.

## 10) prepare 캐시 키 설계
캐시 키는 문자열 hash 앞에 버전을 포함합니다.

1. 정규화 캐시: `qs:norm:{version}:{digest}`
2. 입력 요소: `raw|locale|version`
3. TTL 기본값: `QS_NORM_CACHE_TTL_SEC=3600`

알고리즘 변경 시 `QS_NORM_CACHE_VERSION`만 올리면 안전하게 캐시를 교체할 수 있습니다.

## 11) 품질 디버깅 시 확인할 필드
prepare 결과를 검증할 때는 아래를 함께 봅니다.

1. `query.final`과 `query.finalSource`
2. `detected.mode`/`detected.isIsbn`
3. `understanding.entities`와 `constraints.residualText`
4. `retrievalHints.filters`와 `preferredLogicalFields`

이 네 가지를 보면 “왜 특정 검색 전략이 선택됐는지”가 드러납니다.
