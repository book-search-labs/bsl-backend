# OpenSearch Ingest (Vector)

## Embedding provider
Default provider is MIS.

Required env:
- `EMBED_PROVIDER=mis`
- `MIS_URL=http://localhost:8005`

Optional:
- `EMBED_MODEL` (model label)
- `EMBED_BATCH_SIZE`
- `EMBED_TIMEOUT_SEC`
- `EMBED_MAX_RETRY`
- `EMBED_FALLBACK_TO_TOY` (0/1)
- `EMBED_NORMALIZE` (1/0)

## Embedding cache
- `EMBED_CACHE=off|sqlite|redis`
- `EMBED_CACHE_PATH=data/cache/emb.sqlite`
- `EMBED_CACHE_TTL_SEC=0`
- `EMBED_CACHE_REDIS_URL=redis://localhost:6379/0`

Cache key is based on `vector_text_hash + model + normalize`.

## Deadletters
- `data/nlk/deadletter/embed_fail_deadletter.ndjson`
- `data/nlk/deadletter/books_vec_deadletter.ndjson`

## Example
```bash
EMBED_PROVIDER=mis MIS_URL=http://localhost:8005 EMBED_MODEL=bge-m3 EMBED_CACHE=sqlite ENABLE_VECTOR_INDEX=1 \
  python scripts/ingest/ingest_opensearch.py
```
