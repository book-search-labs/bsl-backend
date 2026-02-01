# B-0281 — OpenSearch RAG Index 설계: docs_doc_v* + docs_vec_v* (highlight/citations 키 고정)

## Goal
RAG retrieval을 위한 OpenSearch 인덱스 2종을 설계/운영 가능하게 만든다.

- `docs_doc_v1`: BM25 + filters + highlight/snippet
- `docs_vec_v1`: kNN vector + metadata
- alias:
  - `docs_doc_read/docs_doc_write`
  - `docs_vec_read/docs_vec_write`
- citations를 위해 **chunk join 키(`chunk_id`)를 고정**

## Background
- RAG는 “문서 검색 + 벡터 검색”을 섞는다.
- 인덱스를 분리하면:
  - 운영 튜닝(샤드/refresh/merge)
  - reindex/alias swap이 쉬움
  - 스키마 진화가 편함

## Scope
### 1) docs_doc_v1 mapping (필수)
- fields:
  - `doc_id` (keyword)
  - `chunk_id` (keyword)  ← citations 핵심키
  - `title` (text + keyword subfield)
  - `heading_path` (text/keyword)
  - `content` (text, analyzer=ko)
  - `source_uri` (keyword)
  - `page` (int)
  - `order_no` (int)
  - `updated_at` (date)
  - `meta` (object/flattened)
- query support:
  - multi_match(title, heading_path, content)
  - highlight(content)
  - filters(meta, updated_at)

### 2) docs_vec_v1 mapping (필수)
- fields:
  - `chunk_id` (keyword)
  - `doc_id` (keyword)
  - `vector` (knn_vector)
  - `title`, `heading_path` (keyword for metadata)
  - `updated_at`, `meta`
- kNN:
  - HNSW params(기본값으로 시작)

### 3) Index ops (필수)
- templates/settings:
  - shards/replicas (local=1 replica=0)
  - refresh interval (ingest 시 느리게)
- alias strategy:
  - write→read swap 지원
- reindex:
  - B-0223 index-writer 재사용 가능 구조 고려

### 4) Retrieval contract(필수)
- Search Service가 retrieval 후 반환해야 할 최소:
  - chunk_id, doc_id, title, heading_path, source_uri, page, highlight/snippet, score
- 이걸 그대로 citations 카드에 씀.

## Non-goals
- Embedding 모델 선택/서빙(=B-0266a/B-0270 확장)
- RAG chat endpoint(=B-0282)

## DoD
- 인덱스/템플릿/alias 생성 스크립트(Flyway or bootstrap) 존재
- 샘플 1k chunks 인덱싱 후:
  - BM25 검색 + highlight 정상
  - kNN 검색 정상
  - chunk_id로 조인 가능한 응답 형태 확인
- alias swap 리허설 완료

## Codex Prompt
Design RAG OpenSearch indices:
- Create docs_doc_v1 and docs_vec_v1 mappings with stable chunk_id join keys.
- Add read/write aliases and index templates/settings for ingest vs serving.
- Provide bootstrap scripts and a smoke test that indexes sample chunks and validates BM25+highlight and kNN retrieval.
