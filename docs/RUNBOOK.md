# Runbook (Local)

## Local OpenSearch v1.1 (Full Set)
Start: `./scripts/local_up.sh`
Check: `curl http://localhost:9200`
Check aliases: `curl -s http://localhost:9200/_cat/aliases?v`
Autocomplete smoke: `curl -s -XPOST http://localhost:9200/ac_suggest_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"text":"해"}},"size":5}'`
Author smoke: `curl -s -XPOST http://localhost:9200/authors_doc_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"name_ko":"롤링"}},"size":5}'`
Series smoke: `curl -s -XPOST http://localhost:9200/series_doc_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"name":"해리"}},"size":5}'`
Stop: `./scripts/local_down.sh`

## Local OpenSearch v1.1
Start: `./scripts/local_up.sh`
Check: `curl http://localhost:9200`
Check aliases: `curl -s http://localhost:9200/_cat/aliases?v`
Lexical smoke: `curl -s -XPOST http://localhost:9200/books_doc_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"title_ko":"해리"}},"size":3}'`
Vector smoke: `curl -s -XPOST http://localhost:9200/books_vec_read/_search -H 'Content-Type: application/json' -d "{\"size\":3,\"query\":{\"knn\":{\"embedding\":{\"vector\":$(python3 -c 'import hashlib,random,json; seed=int(hashlib.sha256(b"b1").hexdigest()[:8],16); r=random.Random(seed); print(json.dumps([round(r.random(),6) for _ in range(1024)]))'),\"k\":3}}}}"`
Stop: `./scripts/local_down.sh`

## Search Service (Local)
Start OpenSearch: `./scripts/local_up.sh`
Run service: `cd services/search-service && ./gradlew bootRun`
Test search: `curl -s -XPOST http://localhost:8080/search -H 'Content-Type: application/json' -d '{"query":{"raw":"해리"}}'`
Test book detail: `curl -s http://localhost:8080/books/b1`
Test autocomplete: `curl -s "http://localhost:8080/autocomplete?q=har&size=10"`

## Ranking Service (Local)
Run service: `cd services/ranking-service && ./gradlew bootRun`
Test rerank: `curl -s -XPOST http://localhost:8082/rerank -H 'Content-Type: application/json' -d '{"query":{"text":"해리"},"candidates":[{"doc_id":"b1","features":{"rrf_score":0.167,"lex_rank":1,"vec_rank":2,"issued_year":1999,"volume":1,"edition_labels":["recover"]}}],"options":{"size":10}}'`
