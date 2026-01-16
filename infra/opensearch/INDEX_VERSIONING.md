# OpenSearch Index Versioning (Blue/Green) — books

## Naming
- Physical index: `books_v1`, `books_v2`, ...
- Read alias (recommended): `books_current`

## Rules
1. Do not mutate mappings in-place for breaking changes.
  - Create a new index version (e.g., `books_v2`) and reindex.
2. Services should query the alias `books_current` (preferred),
   but MVP can query `books_v1` directly.

## MVP Setup (v1)
1) Create `books_v1` with `infra/opensearch/books_v1.mapping.json`
2) (Optional) Point alias `books_current` -> `books_v1`

## Alias Commands
- Create/Update alias:
```bash
curl -XPOST "$OS_URL/_aliases" -H 'Content-Type: application/json' -d '{
  "actions": [
    { "remove": { "index": "books_v*", "alias": "books_current", "ignore_unavailable": true } },
    { "add":    { "index": "books_v1", "alias": "books_current" } }
  ]
}'
