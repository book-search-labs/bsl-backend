# BSL Backend

Backend services and infrastructure for Book Search Labs (BSL): BFF, query/search/autocomplete/ranking, commerce,
model inference, LLM gateway, and indexing pipelines.

## SSOT & repo map

Source-of-truth order (per `AGENTS.md`):

1) `contracts/` — inter-service/public payload schemas + examples  
2) `data-model/` + `db/` — canonical catalog model + migrations  
3) `infra/opensearch/` — index mappings/analyzers  
4) `docs/` — rationale/runbooks (must not contradict SSOT)

Key directories:
- `services/` — runnable services (Spring Boot + FastAPI)
- `scripts/` — local infra, ingestion, ops, tests
- `apps/` — web-user / web-admin clients

## Quick start (local)

Bring up core infra and seed OpenSearch:
```bash
./scripts/local_up.sh
```

Run Search Service (Spring Boot):
```bash
./gradlew :services:search-service:bootRun
```

Optional: run Query Service (FastAPI):
```bash
cd services/query-service
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Smoke search:
```bash
curl -s -XPOST http://localhost:8080/search \
  -H 'Content-Type: application/json' \
  -d '{"query":{"raw":"harry"}}'
```

Stop infra (removes volumes by default):
```bash
./scripts/local_down.sh
```

Notes:
- `./scripts/local_up.sh` uses `compose.yaml` (MySQL + OpenSearch + Dashboards) and seeds indices.
- For the broader infra stack (Redis/ClickHouse/Redpanda), use `docker compose --profile data up -d`.
- Observability stack: `./scripts/observability_up.sh` (uses `compose.yaml` + `observability` profile).
- Local Ollama: `make local-llm-up` (uses `compose.yaml` + `llm` profile).

## Ingestion & indexing

For full NLK ingestion and OpenSearch bootstrap details, see `docs/RUNBOOK.md` and `scripts/ingest/`.

## Configuration

Environment templates and secret handling: `docs/CONFIG.md`.
- Spring Boot configs: `config/spring/<service>/application-*.yml`
- FastAPI configs: `config/.env.{dev,stage,prod}`

## Tests

Run the standard checks:
```bash
./scripts/test.sh
```

Optional gates (set env vars before running):
- `RUN_SCHEMA_CHECK=1`
- `RUN_EVAL=1`
- `RUN_RERANK_EVAL=1`
- `RUN_CANONICAL_CHECKS=1`
- `RUN_E2E=1`

## Docs to read first

- `Plans.md` — milestone roadmap
- `docs/ARCHITECTURE.md` — system design and flows
- `docs/API_SURFACE.md` — endpoint catalog
- `docs/RUNBOOK.md` — local ops + ingestion
