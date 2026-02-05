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
- `config/spring/outbox-relay/application-*.yml`

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
- `BFF_BUDGET_ENABLED`, `BFF_BUDGET_SEARCH_MS`, `BFF_BUDGET_CHAT_MS`
- `BFF_BUDGET_DEFAULT_MS`, `BFF_BUDGET_RESERVE_MS`
- `BFF_BUDGET_MIN_TIMEOUT_MS`, `BFF_BUDGET_MAX_TIMEOUT_MS`

Search:
- `OPENSEARCH_URL`, `OPENSEARCH_DOC_INDEX`, `OPENSEARCH_VEC_INDEX`
- `RANKING_BASE_URL`
- `EMBEDDING_CACHE_ENABLED`, `EMBEDDING_CACHE_TTL_MS`, `EMBEDDING_CACHE_MAX`
- `EMBEDDING_CACHE_MAX_TEXT`, `EMBEDDING_CACHE_NORMALIZE`
- `SEARCH_VECTOR_CACHE_ENABLED`, `SEARCH_VECTOR_CACHE_TTL_MS`, `SEARCH_VECTOR_CACHE_MAX`
- `SEARCH_VECTOR_CACHE_MAX_TEXT`, `SEARCH_VECTOR_CACHE_NORMALIZE`, `SEARCH_VECTOR_CACHE_DEBUG`
- `SEARCH_VECTOR_PROMOTION_ENABLED`, `SEARCH_VECTOR_PROMOTION_SEPARATORS`
- `SEARCH_FUSION_DEFAULT`, `SEARCH_FUSION_EXPERIMENT_ENABLED`, `SEARCH_FUSION_WEIGHTED_RATE`
- `SEARCH_FUSION_LEX_WEIGHT`, `SEARCH_FUSION_VEC_WEIGHT`
- `SEARCH_GROUPING_ENABLED`, `SEARCH_GROUPING_FILL_VARIANTS`
- `SEARCH_GROUPING_RECOVER_PENALTY`, `SEARCH_GROUPING_SET_PENALTY`, `SEARCH_GROUPING_SPECIAL_PENALTY`

Autocomplete:
- `OPENSEARCH_URL`, `OPENSEARCH_USERNAME`, `OPENSEARCH_PASSWORD`, `OPENSEARCH_AC_INDEX`
- `REDIS_URL`
- `AUTOCOMPLETE_CACHE_ENABLED`, `AUTOCOMPLETE_CACHE_TTL_SECONDS`
- `AUTOCOMPLETE_CACHE_MAX_PREFIX`, `AUTOCOMPLETE_CACHE_MAX_ITEMS`
- `AUTOCOMPLETE_CACHE_KEY_PREFIX`

Ranking:
- `RANKING_PORT`

Outbox Relay:
- `OUTBOX_RELAY_PORT`
- `KAFKA_BOOTSTRAP_SERVERS`
- `OUTBOX_RELAY_ENABLED`, `OUTBOX_RELAY_POLL_INTERVAL_MS`, `OUTBOX_RELAY_BATCH_SIZE`
- `OUTBOX_RELAY_MAX_RETRIES`, `OUTBOX_RELAY_BACKOFF_MS`
- `OUTBOX_RELAY_DLQ_ENABLED`, `OUTBOX_RELAY_DLQ_SUFFIX`
- `OUTBOX_RELAY_PRODUCER`
- `OUTBOX_RELAY_TOPIC_SEARCH_IMPRESSION`, `OUTBOX_RELAY_TOPIC_SEARCH_CLICK`, `OUTBOX_RELAY_TOPIC_SEARCH_DWELL`
- `OUTBOX_RELAY_TOPIC_AC_IMPRESSION`, `OUTBOX_RELAY_TOPIC_AC_SELECT`

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

Observability (shared):
- `TRACE_SAMPLE_PROBABILITY`
- `OTEL_EXPORTER_OTLP_ENDPOINT`

Security (BFF / Commerce):
- `SECURITY_HEADERS_ENABLED`, `SECURITY_FRAME_OPTIONS`, `SECURITY_REFERRER_POLICY`
- `SECURITY_PERMISSIONS_POLICY`, `SECURITY_COOP`, `SECURITY_CORP`
- `SECURITY_HSTS_ENABLED`, `SECURITY_HSTS_MAX_AGE`
- `SECURITY_CSRF_ENABLED`, `SECURITY_CSRF_ALLOWED_ORIGINS`
- `SECURITY_ADMIN_APPROVAL_ENABLED`, `SECURITY_ADMIN_APPROVAL_RISKY_PATHS`
- `SECURITY_ABUSE_ENABLED`, `SECURITY_ABUSE_WINDOW_SECONDS`, `SECURITY_ABUSE_ERROR_THRESHOLD`
- `SECURITY_ABUSE_BLOCK_SECONDS`, `SECURITY_ABUSE_ERROR_STATUSES`
- `SECURITY_PII_ENABLED`, `SECURITY_PII_MASK`, `SECURITY_PII_KEYS`
