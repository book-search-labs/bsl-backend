# Ranking Service (MVP)

## Run
```bash
cd services/ranking-service
./gradlew bootRun
```

## MIS Integration
Rerank attempts MIS scoring when `MIS_ENABLED=true`. If MIS is unavailable, it degrades to Stage1
heuristic ranking and then to toy fallback.

Env:
- `MIS_ENABLED` (default: false)
- `MIS_BASE_URL` (default: http://localhost:8005)
- `MIS_TIMEOUT_MS` (default: 200)
- `MIS_MODEL_ID` (default: empty; use MIS registry active)
- `MIS_TASK` (default: rerank)

## Feature Spec + Store
- Feature spec: `config/features.yaml` (set `FEATURE_SPEC_PATH` to override)
- Local feature store: `config/feature_store.json` (set `FEATURE_STORE_PATH` to override)
- Current feature spec version: `rs.fs.v1`
- Stage debug returns per-hit feature snapshots in `debug.raw_features` / `debug.features`

Guardrails (env overrides):
- `RERANK_MAX_CANDIDATES`
- `RERANK_MAX_TOP_N`
- `RERANK_MAX_MIS_CANDIDATES`
- `RERANK_MIN_CANDIDATES_MIS`
- `RERANK_MIN_QUERY_LEN_MIS`
- `RERANK_TIMEOUT_MS_MAX`

## Score Cache
MIS rerank scores are cached by `rerank:{model}:{query_hash}:{doc_id}`.

Env:
- `RERANK_CACHE_ENABLED` (default: true)
- `RERANK_CACHE_TTL_SECONDS` (default: 900)
- `RERANK_CACHE_MAX_ENTRIES` (default: 10000)

Metrics:
- `rs_rerank_cache_hit_total`
- `rs_rerank_cache_miss_total`
- `rs_mis_calls_total`

## 2-Stage Rerank
Backward-compatible options:
- `options.rerank=true|false` (legacy bool)
- `options.rerank.stage1.enabled` / `topK` / `model`
- `options.rerank.stage2.enabled` / `topK` / `model`
- `options.model` (global model override for stage2)

Default behavior:
- Stage1 disabled
- Stage2 enabled
- timeout budget split 40/60 when both stages are enabled

Debug includes `debug.stage_details.stage1|stage2` with applied/skip/failure reason and cache stats.

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

curl -s -XPOST http://localhost:8082/rerank \
  -H 'Content-Type: application/json' \
  -d '{"query":{"text":"harry potter"},"candidates":[{"doc_id":"b1","features":{"rrf_score":0.167,"lex_rank":1,"vec_rank":2}},{"doc_id":"b2","features":{"rrf_score":0.150,"lex_rank":2,"vec_rank":1}}],"options":{"size":10,"debug":true,"model":"rerank_ltr_baseline_v1","rerank":{"stage1":{"enabled":true,"topK":20},"stage2":{"enabled":true,"topK":10}}}}'
```
