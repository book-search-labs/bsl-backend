# Autocomplete Service

Autocomplete Service serves query suggestions with a hot-cache + fallback pattern.

## Runtime behavior
- Reads top prefixes from Redis hot cache first (`source=redis`).
- Falls back to OpenSearch prefix query on miss (`source=opensearch`).
- Returns normalized suggestion IDs/text/scores for UI selection handling.

## Event responsibility (current implementation)
- Suggestion select/impression events are emitted by **BFF** (`/autocomplete/select`), not by this service.
- This service focuses on suggestion retrieval only.

## Run (local)
```bash
cd /path/to/bsl-backend
./gradlew :services:autocomplete-service:bootRun
```

Default port: `8081` (override with `AUTOCOMPLETE_PORT`).

## Key config
- OpenSearch: `OPENSEARCH_URL`, `OPENSEARCH_USERNAME`, `OPENSEARCH_PASSWORD`
- Redis cache policy is controlled by deployment env (TTL/size) where enabled.

## Quick smoke
```bash
curl -s "http://localhost:8081/v1/autocomplete?q=harry&size=5"
```
