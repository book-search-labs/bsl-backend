# Runbook (Local)

## Local OpenSearch v1.1 (Full Set)
Start: `./scripts/local_up.sh`
Check: `curl http://localhost:9200`
Check aliases: `curl -s http://localhost:9200/_cat/aliases?v`
Autocomplete smoke: `curl -s -XPOST http://localhost:9200/ac_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"text":"해"}},"size":5}'`
Author smoke: `curl -s -XPOST http://localhost:9200/authors_doc_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"name_ko":"롤링"}},"size":5}'`
Series smoke: `curl -s -XPOST http://localhost:9200/series_doc_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"name":"해리"}},"size":5}'`
Stop: `./scripts/local_down.sh`

Optional entity indices (authors/series):
- Skip entity indices: `ENABLE_ENTITY_INDICES=0 ./scripts/local_up.sh`
- Authors local fallback mapping: `infra/opensearch/authors_doc_v1.local.mapping.json`

## Local OpenSearch v1.1
Start: `./scripts/local_up.sh`
Check: `curl http://localhost:9200`
Check aliases: `curl -s http://localhost:9200/_cat/aliases?v`
Lexical smoke: `curl -s -XPOST http://localhost:9200/books_doc_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"title_ko":"해리"}},"size":3}'`
Vector smoke: `curl -s -XPOST http://localhost:9200/books_vec_read/_search -H 'Content-Type: application/json' -d "{\"size\":3,\"query\":{\"knn\":{\"embedding\":{\"vector\":$(python3 -c 'import hashlib,random,json; seed=int(hashlib.sha256(b"b1").hexdigest()[:8],16); r=random.Random(seed); print(json.dumps([round(r.random(),6) for _ in range(1024)]))'),\"k\":3}}}}"`
Stop: `./scripts/local_down.sh`

## NLK Ingestion (Local)
Data root: `./data/nlk` (override with `NLK_DATA_DIR=/path/to/nlk`)
Raw files: `./data/nlk/raw`

Start stack: `./scripts/local_up.sh`
Install deps: `python3 -m pip install -r scripts/ingest/requirements.txt`
Run ingestion: `./scripts/ingest/run_ingest.sh`
MySQL only: `./scripts/ingest/run_ingest_mysql.sh`
OpenSearch only: `./scripts/ingest/run_ingest_opensearch.sh`
Reset + reingest: `RESET=1 ./scripts/ingest/run_ingest.sh`
Targets only: `INGEST_TARGETS=mysql` or `INGEST_TARGETS=opensearch`
Fast mode (bigger batches, skip entity indices): `FAST_MODE=1 ./scripts/ingest/run_ingest.sh`
Fast mode also uses `RAW_HASH_MODE=record_id` and `STORE_BIBLIO_RAW=0` unless overridden.
`run_ingest_mysql.sh` defaults to `FAST_MODE=1` (override with `FAST_MODE=0`).
Fast mode enables bulk MySQL loads (`MYSQL_BULK_MODE=1`) unless overridden.
Bulk load (LOAD DATA LOCAL INFILE): `MYSQL_BULK_MODE=1 MYSQL_LOAD_BATCH=100000 ./scripts/ingest/run_ingest_mysql.sh`
MySQL must allow `local_infile=1` (enabled in docker-compose; restart MySQL after changes).
If you see error 1229 about `local_infile`, it's a GLOBAL-only server variable; ensure the server config has `local_infile=1`.
Tune MySQL batch: `MYSQL_CHUNK_SIZE=100` (reduce if MySQL disconnects)
Checkpoints: `./data/nlk/checkpoints` (deadletters in `./data/nlk/deadletter`)
If MySQL crashes (InnoDB assertion), reset the local volume:
`./scripts/local_down.sh` then `./scripts/local_up.sh` (this clears the MySQL volume).

MySQL counts:
- `mysql -h 127.0.0.1 -u bsl -pbsl bsl -e "SELECT COUNT(*) FROM nlk_raw_nodes;"`
- `mysql -h 127.0.0.1 -u bsl -pbsl bsl -e "SELECT COUNT(*) FROM nlk_biblio_docs;"`
OpenSearch aliases: `curl -s http://localhost:9200/_cat/aliases?v | grep books_doc`
OpenSearch sample: `curl -s -XPOST http://localhost:9200/books_doc_read/_search -H 'Content-Type: application/json' -d '{"size":3,"query":{"match_all":{}}}'`

## Autocomplete Ops Loop (Local)
Install deps: `python3 -m pip install -r scripts/autocomplete/requirements.txt`
Run aggregation (outbox → metrics → OpenSearch/Redis): `python3 scripts/autocomplete/aggregate_events.py`
Defaults:
- OpenSearch alias: `AC_ALIAS=ac_write`
- Redis cache keys: `AUTOCOMPLETE_CACHE_KEY_PREFIX=ac:prefix:`
- Decay half-life: `AC_DECAY_HALF_LIFE_SEC=604800`
If Redis is not available, cache invalidation is skipped.

## Kafka + Outbox Relay (Local)
Start Kafka (Redpanda single-node):
`docker run -d --name bsl-kafka -p 9092:9092 -p 9644:9644 redpandadata/redpanda:latest redpanda start --overprovisioned --smp 1 --memory 1G --reserve-memory 0M --node-id 0 --check=false --advertise-kafka-addr localhost:9092`

Run relay:
```bash
export SPRING_PROFILES_ACTIVE=dev
export SPRING_CONFIG_ADDITIONAL_LOCATION=../../config/spring/outbox-relay/
cd services/outbox-relay-service
./gradlew bootRun
```

Ensure BFF outbox is enabled when emitting events:
`BFF_OUTBOX_ENABLED=true`

Check relay health: `curl -s http://localhost:8095/health`
Metrics: `curl -s http://localhost:8095/metrics`
Replay failed outbox events:
`python3 -m pip install -r scripts/outbox/requirements.txt`
`python3 scripts/outbox/replay_outbox.py --status FAILED --limit 500`

## Search Service (Local)
Start OpenSearch: `./scripts/local_up.sh`
Run service: `cd services/search-service && ./gradlew bootRun`
Test search: `curl -s -XPOST http://localhost:8080/search -H 'Content-Type: application/json' -d '{"query":{"raw":"해리"}}'`
Test book detail: `curl -s http://localhost:8080/books/b1`

## Ranking Service (Local)
Run service: `cd services/ranking-service && ./gradlew bootRun`
Test rerank: `curl -s -XPOST http://localhost:8082/rerank -H 'Content-Type: application/json' -d '{"query":{"text":"해리"},"candidates":[{"doc_id":"b1","features":{"rrf_score":0.167,"lex_rank":1,"vec_rank":2,"issued_year":1999,"volume":1,"edition_labels":["recover"]}}],"options":{"size":10}}'`
