# Runbook (Local)

## Quick Start (Local Search)

Start core infra + seed demo data:
```bash
./scripts/local_up.sh
```

Run Search Service:
```bash
cd services/search-service
./gradlew bootRun
```

Test search:
```bash
curl -s -XPOST http://localhost:8080/search -H 'Content-Type: application/json' -d '{"query":{"raw":"해리"}}'
```

Optional: autocomplete (requires OpenSearch to be up):
```bash
cd services/autocomplete-service
./gradlew bootRun
curl -s "http://localhost:8081/autocomplete?q=해리&size=5"
```

For full data ingestion, see **NLK Ingestion (Local)** below.

## Database Migrations (Flyway)

Start MySQL (if not already running):
```bash
docker compose -f compose.yaml up -d mysql
```

Run Flyway (CLI installed):
```bash
flyway -url=jdbc:mysql://localhost:3306/bsl -user=bsl -password=bsl \
  -locations=filesystem:db/migration info

flyway -url=jdbc:mysql://localhost:3306/bsl -user=bsl -password=bsl \
  -locations=filesystem:db/migration migrate
```

Or use the Flyway Docker image:
```bash
docker run --rm \
  -v "$PWD/db/migration:/flyway/sql:ro" \
  flyway/flyway:10 \
  -url=jdbc:mysql://host.docker.internal:3306/bsl \
  -user=bsl -password=bsl \
  info

docker run --rm \
  -v "$PWD/db/migration:/flyway/sql:ro" \
  flyway/flyway:10 \
  -url=jdbc:mysql://host.docker.internal:3306/bsl \
  -user=bsl -password=bsl \
  migrate
```

If the DB already has tables (not managed by Flyway), baseline once before migrate:
```bash
flyway -url=jdbc:mysql://localhost:3306/bsl -user=bsl -password=bsl \
  -locations=filesystem:db/migration baseline -baselineVersion=<latest_version>
```

Notes:
- `latest_version` is the highest `V*.sql` file in `db/migration`.
- On Linux, replace `host.docker.internal` with your host IP or use `--network host`.

## Local OpenSearch v1.1 (Full Set)

### Start / Stop
```bash
./scripts/local_up.sh
./scripts/local_down.sh
```

### Health + aliases
```bash
curl http://localhost:9200
curl -s http://localhost:9200/_cat/aliases?v
```

### If bootstrap alias update returns 404
The alias cleanup in `scripts/os_bootstrap_indices_v1_1.sh` removes aliases by index pattern
(`books_doc_v1_*`, `books_vec_v*`, etc.). If an alias currently points to an index outside those
patterns, OpenSearch returns 404.

Fix by inspecting aliases and removing the offending alias with the **actual index name**, then rerun:
```bash
curl -s http://localhost:9200/_cat/aliases?v
curl -XPOST http://localhost:9200/_aliases -H 'Content-Type: application/json' -d '{
  "actions":[{"remove":{"index":"<actual_index_name>","alias":"books_doc_read"}}]
}'
OS_URL=http://localhost:9200 scripts/os_bootstrap_indices_v1_1.sh
```

### Smoke checks
```bash
curl -s -XPOST http://localhost:9200/ac_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"text":"해"}},"size":5}'
curl -s -XPOST http://localhost:9200/authors_doc_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"name_ko":"롤링"}},"size":5}'
curl -s -XPOST http://localhost:9200/series_doc_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"name":"해리"}},"size":5}'
```

### Optional entity indices (authors/series)
- Skip entity indices:
  ```bash
  ENABLE_ENTITY_INDICES=0 ./scripts/local_up.sh
  ```
- Authors fallback mapping:
  `infra/opensearch/authors_doc_v1.local.mapping.json`

---

## Local OpenSearch v1.1 (Books Doc/Vec)

### Start / Stop
```bash
./scripts/local_up.sh
./scripts/local_down.sh
```

### Health + aliases
```bash
curl http://localhost:9200
curl -s http://localhost:9200/_cat/aliases?v
```

### Smoke checks
```bash
curl -s -XPOST http://localhost:9200/books_doc_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"title_ko":"해리"}},"size":3}'
curl -s -XPOST http://localhost:9200/books_vec_read/_search -H 'Content-Type: application/json' -d "{\"size\":3,\"query\":{\"knn\":{\"embedding\":{\"vector\":$(python3 -c 'import hashlib,random,json; seed=int(hashlib.sha256(b"b1").hexdigest()[:8],16); r=random.Random(seed); print(json.dumps([round(r.random(),6) for _ in range(1024)]))'),\"k\":3}}}}"
```

---

## NLK Ingestion (Local)

### Data paths
- Data root: `./data/nlk` (override with `NLK_DATA_DIR=/path/to/nlk`)
- Raw files: `./data/nlk/raw`
- Checkpoints: `./data/nlk/checkpoints` (deadletters in `./data/nlk/deadletter`)

### Start stack + install deps
```bash
./scripts/local_up.sh
python3 -m pip install -r scripts/ingest/requirements.txt
```

### Run ingestion
```bash
./scripts/ingest/run_ingest.sh
./scripts/ingest/run_ingest_mysql.sh
./scripts/ingest/run_ingest_opensearch.sh
```

OpenSearch ingest defaults to `EMBED_PROVIDER=mis` and **requires** `MIS_URL`:
```bash
EMBED_PROVIDER=mis MIS_URL=http://localhost:8005 \
  ./scripts/ingest/run_ingest_opensearch.sh
```
If you don’t want embeddings:
```bash
ENABLE_VECTOR_INDEX=0 ./scripts/ingest/run_ingest_opensearch.sh
```
Or use toy embeddings without MIS:
```bash
EMBED_PROVIDER=toy ./scripts/ingest/run_ingest_opensearch.sh
```

OpenSearch ingest now writes:
- `books_doc_write` (BM25)
- `books_vec_write` (vector embeddings; required for hybrid search)
- `ac_write` (autocomplete)
- `authors_doc_write` (optional, when enabled)

### Common overrides
```bash
RESET=1 ./scripts/ingest/run_ingest.sh
INGEST_TARGETS=mysql ./scripts/ingest/run_ingest.sh
INGEST_TARGETS=opensearch ./scripts/ingest/run_ingest.sh
FAST_MODE=1 ./scripts/ingest/run_ingest.sh
ENABLE_VECTOR_INDEX=0 ./scripts/ingest/run_ingest_opensearch.sh
```

Notes:
- Fast mode also uses `RAW_HASH_MODE=record_id` and `STORE_BIBLIO_RAW=0` unless overridden.
- `run_ingest_mysql.sh` defaults to `FAST_MODE=1` (override with `FAST_MODE=0`).
- Fast mode enables bulk MySQL loads (`MYSQL_BULK_MODE=1`) unless overridden.
- Bulk load:
  ```bash
  MYSQL_BULK_MODE=1 MYSQL_LOAD_BATCH=100000 ./scripts/ingest/run_ingest_mysql.sh
  ```
- MySQL must allow `local_infile=1` (enabled in docker-compose; restart MySQL after changes).
- If you see error 1229 about `local_infile`, it's a GLOBAL-only server variable; ensure the server config has `local_infile=1`.
- Tune MySQL batch: `MYSQL_CHUNK_SIZE=100` (reduce if MySQL disconnects).
- If MySQL crashes (InnoDB assertion), reset the local volume:
  ```bash
  ./scripts/local_down.sh
  ./scripts/local_up.sh
  ```

### Quick verification
```bash
mysql -h 127.0.0.1 -u bsl -pbsl bsl -e "SELECT COUNT(*) FROM nlk_raw_nodes;"
mysql -h 127.0.0.1 -u bsl -pbsl bsl -e "SELECT COUNT(*) FROM nlk_biblio_docs;"
curl -s http://localhost:9200/_cat/aliases?v | grep books_doc
curl -s -XPOST http://localhost:9200/books_doc_read/_search -H 'Content-Type: application/json' -d '{"size":3,"query":{"match_all":{}}}'
```

---

## Autocomplete Ops Loop (Local)

```bash
python3 -m pip install -r scripts/autocomplete/requirements.txt
python3 scripts/autocomplete/aggregate_events.py
```

Defaults:
- OpenSearch alias: `AC_ALIAS=ac_write`
- Redis cache keys: `AUTOCOMPLETE_CACHE_KEY_PREFIX=ac:prefix:`
- Decay half-life: `AC_DECAY_HALF_LIFE_SEC=604800`

If Redis is not available, cache invalidation is skipped.

---

## Kafka + Outbox Relay (Local)

### Start Kafka (Redpanda single-node)
```bash
docker compose up -d redpanda
```

Alternate (standalone):
```bash
docker run -d --name bsl-kafka -p 9092:9092 -p 9644:9644 redpandadata/redpanda:latest redpanda start --overprovisioned --smp 1 --memory 1G --reserve-memory 0M --node-id 0 --check=false --advertise-kafka-addr localhost:9092
```

### Run relay
```bash
export SPRING_PROFILES_ACTIVE=dev
export SPRING_CONFIG_ADDITIONAL_LOCATION=../../config/spring/outbox-relay/
cd services/outbox-relay-service
./gradlew bootRun
```

Ensure BFF outbox is enabled when emitting events:
```bash
BFF_OUTBOX_ENABLED=true
```

Checks:
```bash
curl -s http://localhost:8095/health
curl -s http://localhost:8095/metrics
```

Replay failed outbox events:
```bash
python3 -m pip install -r scripts/outbox/requirements.txt
python3 scripts/outbox/replay_outbox.py --status FAILED --limit 500
```

---

## OLAP (ClickHouse) + Loader (Local)

### Start ClickHouse
```bash
docker compose up -d clickhouse
```

### Run OLAP loader (Kafka → ClickHouse)
```bash
cd services/olap-loader-service
./gradlew bootRun
```

### LTR pipeline
Generate labels:
```bash
python scripts/olap/generate_ltr_labels.py --start-date 2026-01-30 --end-date 2026-01-31
```

Aggregate features:
```bash
python scripts/olap/aggregate_features.py --start-date 2026-01-30 --end-date 2026-01-31
```

Build training dataset (point-in-time join):
```bash
python scripts/olap/build_training_dataset.py --start-date 2026-01-30 --end-date 2026-01-31 --output /tmp/ltr.jsonl
```

Train LTR + export ONNX:
```bash
python3 -m pip install lightgbm onnxmltools pyyaml
python scripts/ltr/train_lambdamart.py --data /tmp/ltr.jsonl --output-dir var/models
```

Register model artifact:
```bash
python scripts/ltr/register_model.py --model-id ltr_lambdamart_v1 --artifact-uri local://models/ltr_lambdamart_v1.onnx --activate
```

Offline eval regression gate:
```bash
python scripts/eval/run_eval.py --run evaluation/runs/sample_run.jsonl --baseline evaluation/baseline.json --gate
```

---

## RAG Docs (Indexing)

Create RAG indices (OpenSearch):
```bash
DOCS_DOC_INDEX=docs_doc_v1_20260131_001 DOCS_VEC_INDEX=docs_vec_v1_20260131_001 ./scripts/os_bootstrap_indices_v1_1.sh
```

Build chunks + embeddings:
```bash
python scripts/rag/build_doc_chunks.py --input-dir data/rag/docs
python scripts/rag/embed_chunks.py --input var/rag/docs_embed.jsonl --output var/rag/docs_vec.jsonl
```

Index into OpenSearch:
```bash
python scripts/rag/index_chunks.py --docs var/rag/docs_doc.jsonl --vec var/rag/docs_vec.jsonl --deletes var/rag/docs_deletes.jsonl
```

---

## Local LLM (Ollama)
```bash
make local-llm-up
curl -fsS http://localhost:11434/v1/models
```

Model (default in `Makefile`):
- `llama3.1:8b-instruct` (override with `LOCAL_LLM_MODEL=...`)

---

## LLM Gateway (Local)
```bash
cd services/llm-gateway-service
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

Example env (OpenAI-compatible local LLM):
```bash
export LLM_PROVIDER=openai_compat
export LLM_BASE_URL=http://localhost:11434/v1
export LLM_API_KEY=
export LLM_MODEL=llama3.1:8b-instruct
export LLM_TIMEOUT_MS=15000
export LLM_MAX_TOKENS=512
export LLM_TEMPERATURE=0.2
```

QS env (optional model label pass-through):
```bash
export QS_LLM_URL=http://localhost:8010
export QS_LLM_MODEL=llama3.1:8b-instruct
```

---

## Chat smoke test (BFF → QS → LLMGW)
```bash
./scripts/smoke_chat.sh
```

---

## Search Service (Local)
```bash
./scripts/local_up.sh
cd services/search-service
./gradlew bootRun
```

Tests:
```bash
curl -s -XPOST http://localhost:8080/search -H 'Content-Type: application/json' -d '{"query":{"raw":"해리"}}'
curl -s http://localhost:8080/books/b1
```

---

## Ranking Service (Local)
```bash
cd services/ranking-service
./gradlew bootRun
```

Test rerank:
```bash
curl -s -XPOST http://localhost:8082/rerank -H 'Content-Type: application/json' -d '{"query":{"text":"해리"},"candidates":[{"doc_id":"b1","features":{"rrf_score":0.167,"lex_rank":1,"vec_rank":2,"issued_year":1999,"volume":1,"edition_labels":["recover"]}}],"options":{"size":10}}'
```

---

# Phase 9 — Observability & Operations (Production)

## Observability stack (local)
```bash
./scripts/observability_up.sh
# Grafana: http://localhost:3000
# Prometheus: http://localhost:9090
# Tempo: http://localhost:3200
# Loki: http://localhost:3100
# Metabase: http://localhost:3001
```

Stop:
```bash
./scripts/observability_down.sh
```

## MySQL backup / restore
Backup:
```bash
./scripts/mysql_backup.sh
```

Restore (from a backup file):
```bash
./scripts/mysql_restore.sh /path/to/backup.sql.gz
```

## OpenSearch snapshot / restore
Register snapshot repo + snapshot:
```bash
./scripts/opensearch_snapshot.sh
```

Restore a snapshot:
```bash
./scripts/opensearch_restore.sh SNAPSHOT_NAME
```

Retention cleanup (delete snapshots older than N days):
```bash
SNAPSHOT_RETENTION_DAYS=7 ./scripts/opensearch_snapshot_retention.sh
```

## DR rehearsal (minimum)
1) Take a **MySQL** backup + **OpenSearch** snapshot.
2) Spin up a clean environment.
3) Restore MySQL + OpenSearch.
4) Run smoke tests (search + checkout flow).
5) Document recovery time + gaps.

## Incident response (on-call)
- **SEV1:** system down, data loss risk → page immediately, rollback or failover.
- **SEV2:** partial outage, high error rate → mitigate within 30–60 min.
- **SEV3:** degraded performance, non-critical impact → fix in next business day.

### Standard procedure
1) Triage: validate alert + scope blast radius
2) Mitigate: rollback, disable feature flag, scale resources
3) Communicate: status update to stakeholders
4) Diagnose: root cause + remediation
5) Postmortem: action items + owners

## Release check (prod)
- Health checks green (BFF + Search + Autocomplete + Commerce)
- p95/p99 latency within SLO
- Error rate < 1%
- DB + OpenSearch disk < 80%

## Admin risky-action approval (optional)
If enabled (`SECURITY_ADMIN_APPROVAL_ENABLED=true`), risky admin paths require `x-approval-id`.
Create approval via SQL (example):
```sql
INSERT INTO admin_action_approval (requested_by_admin_id, action, status, approved_by_admin_id)
VALUES (1, 'POST /admin/ops/reindex-jobs/start', 'APPROVED', 2);
```
Then call the API with `x-approval-id` set to the row id.

---

# Phase 10 — Hardening (Optional)
