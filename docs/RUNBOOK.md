# Runbook (Local)

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
