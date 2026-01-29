# B-0281 — OpenSearch RAG Index Design: docs doc v* + docs vec v* (fixed highlight/citations key)

## Goal
RAG retrieval design/operable with two openSearch indexes.

- `docs_doc_v1`: BM25 + filters + highlight/snippet
- `docs_vec_v1`: kNN vector + metadata
- alias:
  - `docs_doc_read/docs_doc_write`
  - `docs_vec_read/docs_vec_write`
- For citations fix **chunk join key( TBD  )**

## Background
- RAG Mix “Document Search + Vector Search”
- When the index is separated:
  - Operation Tuning (Shad/refresh/merge)
  - reindex/alias swap
  - Skima Evolution

## Scope
### 1) docs doc v1 mapping (required)
- fields:
  - `doc_id` (keyword)
  - New  TBD   (keyword) ← citations keykey
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

### 2) docs vec v1 mapping (required)
- fields:
  - `chunk_id` (keyword)
  - `doc_id` (keyword)
  - `vector` (knn_vector)
  - `title`, `heading_path` (keyword for metadata)
  - `updated_at`, `meta`
- kNN:
  - HNSW params

### Index ops
- templates/settings:
  - shards/replicas (local=1 replica=0)
  - refresh interval
- alias strategy:
  - write→read swap support
- reindex:
  - B-0223 index-writer reusable structure consideration

### 4) Retrieval contract(Required)
- Search Service must return after retrieval:
  - chunk_id, doc_id, title, heading_path, source_uri, page, highlight/snippet, score
- by the citations card as this.

## Non-goals
- Embedding Model Selection / Serving(=B-0266a/B-0270 Expansion)
- RAG chat endpoint(=B-0282)

## DoD
- index/template/alias creation script (Flyway or bootstrap) presence
- Sample 1k chunks after indexing:
  - BM25 search + highlight top
  - KNN Search Top
  - chunk id
- alias swap rehearsal completed

## Codex Prompt
Design RAG OpenSearch indices:
- Create docs_doc_v1 and docs_vec_v1 mappings with stable chunk_id join keys.
- Add read/write aliases and index templates/settings for ingest vs serving.
- Provide bootstrap scripts and a smoke test that indexes sample chunks and validates BM25+highlight and kNN retrieval.
