# Ranking Service (MVP)

## Run
```bash
cd services/ranking-service
./gradlew bootRun
```

## MIS Integration
Rerank attempts MIS scoring when `MIS_ENABLED=true`. If MIS is unavailable, it falls back to the heuristic
toy scorer.

Env:
- `MIS_ENABLED` (default: false)
- `MIS_BASE_URL` (default: http://localhost:8005)
- `MIS_TIMEOUT_MS` (default: 200)
- `MIS_MODEL_ID` (default: empty; use MIS registry active)
- `MIS_TASK` (default: rerank)

## Feature Spec + Store
- Feature spec: `config/features.yaml` (set `FEATURE_SPEC_PATH` to override)
- Local feature store: `config/feature_store.json` (set `FEATURE_STORE_PATH` to override)

Guardrails (env overrides):
- `RERANK_MAX_CANDIDATES`
- `RERANK_MAX_TOP_N`
- `RERANK_MAX_MIS_CANDIDATES`
- `RERANK_MIN_CANDIDATES_MIS`
- `RERANK_MIN_QUERY_LEN_MIS`
- `RERANK_TIMEOUT_MS_MAX`

## Test
```bash
cd services/ranking-service
./gradlew test
```

## Curl
```bash
curl -s http://localhost:8082/health

curl -s -XPOST http://localhost:8082/rerank \
  -H 'Content-Type: application/json' \
  -d '{"query":{"text":"harry potter"},"candidates":[{"doc_id":"b1","features":{"rrf_score":0.167,"lex_rank":1,"vec_rank":2,"issued_year":1999,"volume":1,"edition_labels":["recover"]}},{"doc_id":"b2","features":{"rrf_score":0.150,"lex_rank":2,"vec_rank":1,"issued_year":2000,"volume":2,"edition_labels":[]}}],"options":{"size":10}}'
```
