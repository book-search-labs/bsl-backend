# Configuration & Secrets (per-env)

This repo follows a **per-environment config** policy to keep local/dev/stage/prod isolated and ready for secret rotation.

## 1) Config layout

### Spring Boot services
Per-env templates live under `config/spring/<service>/`:
- `config/spring/bff/application-dev.yml`
- `config/spring/bff/application-stage.yml`
- `config/spring/bff/application-prod.yml`
- `config/spring/search/application-*.yml`
- `config/spring/autocomplete/application-*.yml`
- `config/spring/ranking/application-*.yml`

These files contain **environment-variable placeholders** only (no secrets).
Stage/prod files intentionally omit default values to **fail fast** when env vars are missing.

**How to run (example: BFF, dev):**
```bash
export SPRING_PROFILES_ACTIVE=dev
export SPRING_CONFIG_ADDITIONAL_LOCATION=../../config/spring/bff/
cd services/bff-service
./gradlew bootRun
```

**Stage/prod** uses the same pattern, but with `SPRING_PROFILES_ACTIVE=stage|prod` and
real env values injected by your secret manager.

### FastAPI / misc services
Per-env templates live at:
- `config/.env.dev`
- `config/.env.stage`
- `config/.env.prod`

**How to run (example: Query Service, dev):**
```bash
set -a
source config/.env.dev
set +a
cd services/query-service
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

## 2) Secret injection

- **dev**: `config/.env.dev` (or local `.env`) + docker compose secrets when available
- **stage/prod** (choose one):
  - AWS SSM Parameter Store / Secrets Manager
  - Vault
  - Kubernetes Secrets

**Rule:** secrets must not be committed. Use env injection at runtime.

## 3) Rotation strategy (v1)

Use versioned keys to enable safe rotation:
- `OPENAI_API_KEY_v1`, `OPENAI_API_KEY_v2`
- `PAYMENT_TOKEN_v1`, `PAYMENT_TOKEN_v2`

**Procedure (manual v1):**
1) Inject `*_v2` alongside `*_v1`.
2) Switch `*_ACTIVE` pointer (or update app config to read v2).
3) Deploy and verify.
4) Remove v1 after confirmation.

## 4) Fail-fast & log hygiene

- Stage/prod configs **omit defaults** for required values so startup fails early.
- Never log secrets. If you must log config, **mask** sensitive values.

## 5) Reference env keys (common)

Spring (shared):
- `LOG_LEVEL`
- `CORS_ALLOW_ORIGINS`, `CORS_ALLOW_METHODS`, `CORS_ALLOW_HEADERS`, `CORS_EXPOSED_HEADERS`, `CORS_ALLOW_CREDENTIALS`

BFF:
- `DB_URL`, `DB_USER`, `DB_PASSWORD`, `REDIS_URL`
- `QS_BASE_URL`, `SS_BASE_URL`, `AC_BASE_URL`
- `INDEX_WRITER_BASE_URL`, `INDEX_WRITER_TIMEOUT_MS`

Search:
- `OPENSEARCH_URL`, `OPENSEARCH_DOC_INDEX`, `OPENSEARCH_VEC_INDEX`
- `RANKING_BASE_URL`

Autocomplete:
- `OPENSEARCH_URL`, `OPENSEARCH_USERNAME`, `OPENSEARCH_PASSWORD`, `OPENSEARCH_AC_INDEX`

Ranking:
- `RANKING_PORT`

FastAPI (shared):
- `BSL_ENV`, `BSL_TENANT_ID`, `BSL_LOCALE`, `BSL_TIMEZONE`
- `CORS_ALLOW_ORIGINS`, `CORS_ALLOW_ORIGIN_REGEX`
- `NORMALIZATION_RULES_PATH` (optional)

Index Writer Service:
- `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`
- `OS_URL`, `BOOKS_DOC_ALIAS`, `BOOKS_DOC_READ_ALIAS`
- `BOOKS_DOC_INDEX_PREFIX`, `BOOKS_DOC_MAPPING`, `DELETE_EXISTING`
- `MYSQL_BATCH_SIZE`, `OS_BULK_SIZE`, `OS_RETRY_MAX`, `OS_RETRY_BACKOFF_SEC`
- `REINDEX_MAX_FAILURES`, `REINDEX_BULK_DELAY_SEC`
- `OS_REFRESH_INTERVAL_BULK`, `OS_REFRESH_INTERVAL_POST`
