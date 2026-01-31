# OpenSearch Index Versioning (Blue/Green)

## Naming
- Physical index: `books_v1`, `books_v2`, ...
- Read alias (recommended): `books_current`

RAG docs:
- Physical index: `docs_doc_v1_YYYYMMDD_001`, `docs_vec_v1_YYYYMMDD_001`, ...
- Read alias: `docs_doc_read`, `docs_vec_read`
- Write alias: `docs_doc_write`, `docs_vec_write`

## Rules
1. Do not mutate mappings in-place for breaking changes.
  - Create a new index version (e.g., `books_v2`) and reindex.
2. Services should query the alias `books_current` (preferred),
   but MVP can query `books_v1` directly.

## MVP Setup (v1)
1) Create `books_v1` with `infra/opensearch/books_v1.mapping.json`
2) (Optional) Point alias `books_current` -> `books_v1`

RAG docs:
1) Create `docs_doc_v1_*` with `infra/opensearch/docs_doc_v1.mapping.json`
2) Create `docs_vec_v1_*` with `infra/opensearch/docs_vec_v1.mapping.json`
3) Point aliases `docs_doc_read/write`, `docs_vec_read/write` accordingly

## Alias Commands
- Create/Update alias:
```bash
curl -XPOST "$OS_URL/_aliases" -H 'Content-Type: application/json' -d '{
  "actions": [
    { "remove": { "index": "books_v*", "alias": "books_current", "ignore_unavailable": true } },
    { "add":    { "index": "books_v1", "alias": "books_current" } }
  ]
}'
