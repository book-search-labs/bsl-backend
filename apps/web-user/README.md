# BSL Web User

## Run (local)
```bash
cd apps/web-user
npm install
cp .env.example .env
npm run dev -- --port 5174
```

## Environment
```
VITE_BFF_BASE_URL=http://localhost:8088
VITE_API_MODE=bff_only
VITE_ALLOW_DIRECT_FALLBACK=false
VITE_SEARCH_BASE_URL=http://localhost:8080
VITE_QUERY_BASE_URL=http://localhost:8001
VITE_AUTOCOMPLETE_SERVICE_BASE_URL=http://localhost:8081
```

- `VITE_ALLOW_DIRECT_FALLBACK=true` enables legacy direct-call fallback only for migration/debug.

## Example URLs
- http://localhost:5174/
- http://localhost:5174/search?q=%ED%95%B4%EB%A6%AC&size=5&vector=true

## BFF search curl
```bash
curl -s -X POST http://localhost:8088/search \
  -H 'Content-Type: application/json' \
  -d '{"query":{"raw":"해리"},"options":{"size":5,"from":0,"enableVector":true}}'
```

## Search Service curl (qc.v1.1)
```bash
curl -s -X POST http://localhost:8080/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query_context_v1_1": {
      "meta": {
        "schemaVersion": "qc.v1.1",
        "traceId": "trace_web_user_demo",
        "requestId": "req_web_user_demo",
        "tenantId": "books",
        "timestampMs": 1710000000000,
        "locale": "ko-KR",
        "timezone": "Asia/Seoul"
      },
      "query": {
        "raw": "haeri",
        "norm": "haeri",
        "final": "haeri"
      },
      "retrievalHints": {
        "queryTextSource": "query.final",
        "lexical": {
          "enabled": true,
          "topKHint": 50,
          "operator": "and",
          "preferredLogicalFields": ["title_ko", "author_ko"]
        },
        "vector": {
          "enabled": true,
          "topKHint": 50,
          "fusionHint": { "method": "rrf", "k": 60 }
        },
        "rerank": { "enabled": false, "topKHint": 10 },
        "filters": [],
        "fallbackPolicy": []
      }
    },
    "options": { "size": 10, "from": 0, "debug": true }
  }'
```
