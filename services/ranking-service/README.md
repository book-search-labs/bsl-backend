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
