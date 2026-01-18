# Autocomplete Service

## Run (local)
```bash
cd /path/to/bsl-backend
./gradlew :services:autocomplete-service:bootRun
```

Default port: `8081` (from `src/main/resources/application.yml`, override with `AUTOCOMPLETE_PORT`).

OpenSearch config (env):
- `OPENSEARCH_URL` (default `http://localhost:9200`)
- `OPENSEARCH_USERNAME` / `OPENSEARCH_PASSWORD` (optional)

## Test curl
```bash
curl -s "http://localhost:8081/v1/autocomplete?q=harry&size=5"
```
