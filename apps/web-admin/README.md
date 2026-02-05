# Web Admin

Admin UI for the Book Search stack.

## Run (dev)

```bash
cd apps/web-admin
npm install
cp .env.example .env
npm run dev
```

## Environment

```
VITE_BFF_BASE_URL=http://localhost:8088
VITE_ADMIN_API_MODE=bff_only
VITE_ADMIN_ALLOW_DIRECT_FALLBACK=false
VITE_INDEX_WRITER_BASE_URL=http://localhost:8090
VITE_BSL_API_BASE_URL=http://localhost:8080
VITE_API_BASE_URL=http://localhost:8080
VITE_QUERY_BASE_URL=http://localhost:8001
VITE_SEARCH_BASE_URL=http://localhost:8080
```

- `VITE_ADMIN_ALLOW_DIRECT_FALLBACK=true` enables legacy direct fallback (recommended only for read-only migration checks).

## Routes

- /dashboard
- /dashboard/v1
- /dashboard/v2
- /dashboard/v3
- /search-playground
- /tools/playground
- /tools/compare
- /ops/index/indices
- /ops/index/doc-lookup
- /ops/jobs
- /settings
