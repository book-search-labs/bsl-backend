# B-0398 — OpenSearch v2 스키마/DSL 일괄 교체 (books_doc v2 + ac_candidates v2 + books_vec v5)

## Priority
- P0 (검색 정확도/성능/운영 안정성 핵심)

## Goal
기존 v1 검색 스키마/DSL을 전면 교체해, 다음을 동시에 달성한다.
- `books_doc v2` 필드 계약(`*.auto/*.compact/*.exact`, `author_names_*`, `series_name`)으로 본문 검색 표준화
- `ac_candidates v2` 자동완성 스키마를 books v2 정규화 규칙과 정렬
- `books_vec v5`에 서빙 필터 필드 복제(`is_hidden` 포함)로 벡터 pre-filter 일관화
- `/search`가 OpenSearch로 전송하는 Query DSL 1~10을 v2 템플릿 기준으로 일괄 교체

## Normative Spec
- 구현에 사용해야 하는 스키마/DSL 원문 템플릿은 아래 문서를 기준으로 한다.
- [tasks/backlog/specs/B-0398-opensearch-v2-spec-pack.md](/Users/seungyoonkim/sideProjects/bsl/bsl-backend/tasks/backlog/specs/B-0398-opensearch-v2-spec-pack.md)

## Why
- 현재 DSL이 존재하지 않는 필드(`*.edge`, `*.ngram`, `*.raw`) 및 wildcard 패턴에 의존해 정확도/성능이 불안정함
- nested `authors` 직접 검색은 복잡성과 비용이 커서 `author_names_*` flat 검색으로 통일이 필요함
- 벡터 인덱스에서 `is_hidden` 및 공통 필터를 pre-filter 못 걸어 숨김 문서 노출/리콜 저하 위험이 있음

## Preconditions (필수)
- OpenSearch plugin 설치
  - `analysis-icu`
  - `analysis-nori`
- OpenSearch 노드 파일 준비 (`config/analysis`)
  - `analysis/userdict_ko.txt`
  - `analysis/synonyms_ko.txt`
  - `analysis/synonyms_en.txt`

## Scope
### 1) books_doc v2 인덱스 스키마/alias 도입
- 신규 매핑 파일 추가: `infra/opensearch/books_doc_v2.mapping.json`
- 분석기/정규화기 추가
  - `ko_text_index/search`, `en_text_index/search`
  - `univ_auto_*`, `univ_compact_*`
  - `keyword_norm`, `isbn_norm`
- 필드 계약
  - 본문 검색 필드: `title_ko`, `title_en`, `series_name`, `author_names_ko`, `author_names_en`, `publisher_name`
  - multi-field: `.exact`, `.auto(index_prefixes)`, `.compact`
  - `authors`는 nested로 저장 유지(검색 대상 아님)
- alias cutover
  - `books_doc_read`
  - `books_doc_write` (`is_write_index=true`)

### 2) ac_candidates v2 인덱스 스키마/alias 도입
- 신규 매핑 파일 추가: `infra/opensearch/ac_candidates_v2.mapping.json`
- `text_kw` 제거, `text.exact/text.compact/text.compact_kw`로 통일
- books v2와 같은 정규화 규칙(`icu + punct_to_space + compact`) 정렬
- alias cutover
  - `ac_candidates_read`
  - `ac_candidates_write` (`is_write_index=true`)

### 3) books_vec v5 인덱스 스키마/alias 도입
- 신규 매핑 파일 추가: `infra/opensearch/books_vec_v5.mapping.json`
- `knn_vector` 384-d, lucene+hnsw 유지
- 검색 pre-filter를 위한 최소 필드 복제
  - `is_hidden`, `language_code`, `issued_year`, `volume`, `edition_labels`
  - `kdc_node_id`, `kdc_code`, `kdc_edition`, `kdc_path_codes`
  - `category_paths`, `concept_ids`, `identifiers.isbn13/isbn10`
- alias cutover
  - `books_vec_read`
  - `books_vec_write` (`is_write_index=true`)

### 4) /search OpenSearch Query DSL 1~10 전면 교체
- 대상: Search Service가 OpenSearch로 생성/전송하는 DSL 전체
- v2 계약으로 교체
  1. Lexical 기본 검색 (`books_doc_read/_search`)
  2. Lexical Query Override (ISBN 라우팅)
  3. Lexical Query Override (author/title/series/publisher 엔티티)
  4. query text 없는 필터-only 검색 (`match_all`)
  5. Vector kNN (EMBEDDING)
  6. Vector Neural (OPENSEARCH_NEURAL)
  7. Chunk kNN (CHUNK)
  8. hydrate (`_mget`) 유지
  9. 상세조회 (`_doc/{docId}`) 유지
  10. optional filters 매핑 유지(모두 `bool.filter` append)

### 5) 검색 공통 계약 강제
- 제거 대상 전부 삭제
  - `*.ngram`, `*.edge`, `*.raw`, wildcard 쿼리
  - `authors.name_*` 직접 검색
- 숨김 처리 통일
  - 기존 `must_not is_hidden:true` 제거
  - `filter term is_hidden:false`로 통일
- 자동완성/prefix는 `bool_prefix + *.auto(index_prefixes)`로 통일

### 6) ISBN normalize 규칙 반영
- ISBN 라우팅 전 앱 레벨 normalize 구현
  - digits/`X`만 유지, 하이픈/공백/전각 숫자 제거
- `identifiers.isbn13/isbn10` term 조회에 normalize 값 사용

### 7) 인덱싱 파이프라인 반영
- `books_doc` 색인 문서에 아래 필드 생성
  - `series_name` (없으면 미포함)
  - `author_names_ko`(string[])
  - `author_names_en`(string[])
- `books_vec` 색인 문서에 필터 필드 복제
  - 최소: `is_hidden` 포함 + v5 매핑 필드

### 8) 자동완성 쿼리 템플릿 교체
- `ac_candidates_read/_search`를 `function_score` + `bool_prefix` + `text.compact` 조합으로 교체
- 랭킹 함수
  - `weight`, `popularity_7d`, `ctr_7d`, `last_seen_at(gauss)`

### 9) 부트스트랩/운영 스크립트 업데이트
- 인덱스 생성/alias 연결 스크립트 v2/v5 대응
  - 신규: `scripts/os_bootstrap_indices_v2.sh` (또는 기존 스크립트 확장)
- blue/green index 생성과 alias swap 지원

## Non-goals
- 벡터 임베딩 모델 교체/재학습
- 랭킹 로직(RRF/가중치) 자체 변경
- 계약 스키마(`contracts/**`)의 구조 변경

## Implementation Notes
- SSOT 우선순위 준수
  - `infra/opensearch/**`를 스키마 SSOT로 반영
  - 구현 변경 순서: `infra/opensearch -> code -> tests -> docs`
- strict mapping 대응
  - 누락 필드로 인한 색인 실패가 없도록 ingest 변환기 선행 수정
- 성능
  - `track_total_hits: false` 기본
  - vector/neural/chunk 쿼리에서 `_source: ["doc_id"]` 사용

## DoD
- `books_doc_v2_*`, `ac_candidates_v2_*`, `books_vec_v5_*` 생성 및 alias 전환 완료
- `/search` 경로에서 생성되는 OpenSearch DSL이 1~10 항목 모두 v2 템플릿과 일치
- 코드베이스에서 금지 필드/패턴이 제거됨
  - `*.edge`, `*.ngram`, `*.raw`, `wildcard`, `authors.name_` 검색
- ingest가 `series_name`, `author_names_ko/en`, `books_vec v5 필터 필드`를 정상 색인
- 자동완성 쿼리가 `text.exact/text.compact/text.compact_kw` 기반으로 동작
- 숨김 문서가 lexical/vector/autocomplete 어디에서도 노출되지 않음
- 회귀 테스트/스모크 통과

## Validation / Test
- 정적 검사
  - `rg`로 금지 필드/패턴 제거 확인
- 인덱스 검증
  - `_mapping`, `_settings`, `_alias` 확인
- 검색 스모크
  - 일반 검색, ISBN 검색, 엔티티 검색(author/title/series/publisher), 필터-only 검색
  - vector/neural/chunk 모드별 필터 동작 확인
- 자동완성 스모크
  - 띄어쓰기/기호/붙여쓰기 변형 질의에서 기대 후보 노출 확인
- 기본 테스트
  - `./scripts/test.sh`

## Expected Files
- `infra/opensearch/books_doc_v2.mapping.json`
- `infra/opensearch/ac_candidates_v2.mapping.json`
- `infra/opensearch/books_vec_v5.mapping.json`
- `infra/opensearch/INDEX_VERSIONING.md` (필요 시 버저닝 절차 보강)
- `scripts/os_bootstrap_indices_v2.sh` (신규 또는 기존 확장)
- `scripts/ingest/ingest_opensearch.py`
- `services/search-service/src/main/java/com/bsl/search/opensearch/OpenSearchGateway.java`
- `services/search-service/src/main/java/com/bsl/search/service/HybridSearchService.java`
- `services/search-service/src/main/java/com/bsl/search/retrieval/*`
- `services/autocomplete-service/**` (쿼리 템플릿 반영)
- `docs/opensearch/*.md`, `docs/RUNBOOK.md` (운영 절차/검증 갱신)

## Rollback
- alias를 이전 인덱스로 즉시 재지정
  - `books_doc_read/write`
  - `books_vec_read/write`
  - `ac_candidates_read/write`
- 새 인덱스는 보존 후 원인 분석

## Codex Prompt
Implement OpenSearch v2 migration pack:
- Introduce `books_doc v2`, `ac_candidates v2`, `books_vec v5` mappings and aliases.
- Replace all Search Service OpenSearch DSL paths (1~10) to the v2 templates.
- Remove legacy fields/wildcards and enforce `is_hidden:false` in `bool.filter`.
- Update ingest transformers for `series_name`, `author_names_*`, and vector filter fields.
- Update autocomplete query template to `bool_prefix + function_score` on v2 fields.
- Add tests, runbook updates, and blue/green alias cutover support.
