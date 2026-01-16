# Ranking Service (MVP)

## Run
```bash
cd services/ranking-service
./gradlew bootRun
```

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
