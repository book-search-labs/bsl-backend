---
title: "04. OpenSearch 매핑 버전과 Alias 기반 전환"
slug: "bsl-backend-series-04-opensearch-mapping-versioning"
series: "BSL Backend Technical Series"
episode: 4
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 04. OpenSearch 매핑 버전과 Alias 기반 전환

## 문제
검색 스키마는 계속 바뀝니다. 기존 인덱스를 직접 수정하면 롤백과 비교 실험이 어려워집니다.

## 1) 버전 규칙과 Alias
기준 문서: `infra/opensearch/INDEX_VERSIONING.md`

- 물리 인덱스: `books_doc_v*`, `books_vec_v*`
- 읽기 alias: `books_doc_read`, `books_vec_read`
- 쓰기 alias: `books_doc_write`

파괴적 변경은 “기존 인덱스 수정”이 아니라 “새 버전 생성 + 재색인 + alias 스왑”으로만 처리합니다.

## 2) 문서 인덱스 매핑 핵심 (`books_doc_v2_1.mapping.json`)
기술적으로 중요한 포인트:

1. `dynamic: strict`
2. 한국어/영어 analyzer 분리
   - `ko_text_index`, `ko_text_search`
   - `en_text_index`, `en_text_search`
3. 동의어/사전 파일 경로 명시
   - `analysis/synonyms_ko.txt`, `analysis/synonyms_en.txt`
   - `analysis/userdict_ko.txt`
4. ISBN normalizer 분리
   - `isbn_norm`

`dynamic: strict` 덕분에 인입 문서 스키마 drift를 초기에 잡을 수 있습니다.

## 3) 벡터 인덱스 매핑 핵심 (`books_vec_v5.mapping.json`)
- `embedding`: `knn_vector`
- `dimension`: `384`
- method: HNSW (`name=hnsw`, `space_type=cosinesimil`)
- 인덱스도 `dynamic: strict`

벡터 차원/space_type이 어긋나면 검색 경로 전체가 무효가 되므로, 스크립트에서 override를 제한적으로만 허용했습니다.

## 4) 부트스트랩 스크립트 (`scripts/os_bootstrap_indices_v1_1.sh`)
이 스크립트는 로컬 인덱스 초기화의 진입점입니다.

핵심 기능:
1. OpenSearch reachability 확인
2. 필수 플러그인 체크
   - `analysis-nori`
   - `analysis-icu`
3. 매핑 파일 존재 검증
4. 환경변수 기반 벡터 파라미터 override
   - `VEC_DIM`, `VEC_SPACE_TYPE`, `VEC_HNSW_M`, `VEC_HNSW_EF_CONSTRUCTION`, `VEC_HNSW_EF_SEARCH`
5. 인덱스 생성 후 alias 연결

## 5) 실전에서 유용했던 점
새 인덱스를 만들고 alias만 교체하면, 같은 쿼리로 전/후 매핑을 비교하기 쉽습니다. side project에서도 실험 반복 속도가 크게 올라갑니다.

## 로컬 실행
```bash
OS_URL=http://localhost:9200 ./scripts/os_bootstrap_indices_v1_1.sh
```

## 6) 문서 매핑 분석기 체인 심화
`books_doc_v2_1.mapping.json`의 핵심은 char_filter + analyzer 조합입니다.

1. `cf_punct_to_space`, `cf_ws_collapse`: 구두점/공백 정규화
2. `ko_nori_userdict`: 사용자 사전 기반 nori tokenizer
3. `ko_pos`: 불필요 품사 제거
4. `syn_ko`/`syn_en`: 검색 시 synonym_graph 확장
5. `isbn_norm`: 숫자/대문자 정규화

즉, 단순 tokenizer 선택이 아니라 질의/문서 양쪽의 정규화 전략을 같이 정의합니다.

## 7) 필드 다중화 설계 이유
`title_ko`, `title_en`, `author_names_ko` 등은 하위 필드를 함께 둡니다.

1. `exact`: keyword normalizer 매칭
2. `auto`: prefix 검색
3. `compact`: 공백 제거 검색
4. `reading`(ko): readingform 기반 검색

한 필드에서 용도를 나누지 않고, 용도별 하위 필드로 쿼리 전략을 분리한 구조입니다.

## 8) 벡터 매핑에서 중요한 튜닝 포인트
`books_vec_v5.mapping.json` 기준 기본값:

1. `dimension=384`
2. `space_type=cosinesimil`
3. HNSW `m=16`, `ef_construction=128`
4. `dynamic: strict`

벡터 임베딩 모델 변경 시에는 차원 불일치를 먼저 확인해야 합니다.

## 9) 부트스트랩 스크립트의 안전장치
`scripts/os_bootstrap_indices_v1_1.sh`는 아래를 강제합니다.

1. OpenSearch 연결 확인
2. 플러그인 설치 확인(`analysis-nori`, `analysis-icu`)
3. 매핑 파일 존재 검증
4. 인덱스 존재 시 `KEEP_INDEX` 정책 반영
5. alias 연결

플러그인 누락 상태를 조기 차단하는 점이 로컬 안정성에 중요합니다.

## 10) 버전 업그레이드 시 권장 절차
1. 새 mapping 파일 생성 (`*_vNext.mapping.json`)
2. 새 물리 인덱스 생성
3. 데이터 적재/검증
4. alias swap
5. 필요 시 기존 인덱스 보존 또는 정리

이 절차를 지키면 기존 검색 경로를 끊지 않고 실험이 가능합니다.
