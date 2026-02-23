# Canonical → OpenSearch Reindex (Local)

This doc describes the **local-only** reindex flow that reads from the canonical MySQL schema and rebuilds the OpenSearch books index.

## What it does
- Optionally deletes existing `books_doc_*` indices and aliases.
- Creates a fresh books index from `infra/opensearch/books_doc_v2.mapping.json`.
- Reads Canonical tables (`material`, `material_agent`, `agent`, `material_identifier`, `material_concept`, `concept`, overrides/merges).
- Denormalizes to books search documents and bulk-indexes into OpenSearch.
- Verifies index count and runs a few sample queries.

## Run (one command)
```bash
./scripts/reindex_books.sh
```

## Requirements
- OpenSearch running at `http://localhost:9200`.
- MySQL running with Canonical tables populated.
- Python deps installed:
```bash
python3 -m pip install -r scripts/ingest/requirements.txt
```

## Environment knobs (optional)
- `OS_URL` (default `http://localhost:9200`)
- `BOOKS_DOC_ALIAS` (default `books_doc_write`)
- `BOOKS_DOC_READ_ALIAS` (default `books_doc_read`)
- `BOOKS_DOC_INDEX_PREFIX` (default `books_doc_v2_local`)
- `BOOKS_DOC_MAPPING` (default `infra/opensearch/books_doc_v2.mapping.json`)
- `DELETE_EXISTING` (default `1`) — delete `books_doc_*` indices before reindex
- `OS_BULK_SIZE` (default `1000`)
- `OS_RETRY_MAX` (default `3`)
- `OS_RETRY_BACKOFF_SEC` (default `1.0`)
- `MYSQL_HOST` (default `127.0.0.1`)
- `MYSQL_PORT` (default `3306`)
- `MYSQL_USER` (default `bsl`)
- `MYSQL_PASSWORD` (default `bsl`)
- `MYSQL_DATABASE` (default `bsl`)
- `MYSQL_BATCH_SIZE` (default `1000`)
- `REINDEX_FAILURE_LOG` (default `./data/reindex_books_failures.ndjson`)

## Output / Verification
The script prints:
- Bulk progress logs (`indexed X (failed Y)`)
- Final count from OpenSearch
- A few sample query hit counts

Failures are logged to `REINDEX_FAILURE_LOG` with doc id + error details.

## Troubleshooting
- **OpenSearch unreachable**: ensure `./scripts/local_up.sh` is running.
- **Count is 0**: verify canonical tables have data (`SELECT COUNT(*) FROM material;`).
- **Bulk errors**: inspect `REINDEX_FAILURE_LOG` for the specific document errors.
- **Mapping errors**: ensure the mapping file exists and matches the document fields.
