#!/usr/bin/env bash
set -euo pipefail

OS_URL="${OS_URL:-http://localhost:9200}"
INDEX_NAME="${INDEX_NAME:-books_v1}"
KEEP_INDEX="${KEEP_INDEX:-0}"
MAPPING_FILE="infra/opensearch/books_v1.mapping.json"

if [ ! -f "$MAPPING_FILE" ]; then
  echo "Mapping file not found: $MAPPING_FILE"
  exit 1
fi

echo "OpenSearch URL: $OS_URL"
echo "Index name: $INDEX_NAME"

# Wait a bit for safety (in case this script is called standalone)
for i in $(seq 1 30); do
  if curl -fsS "$OS_URL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

EXISTS_HTTP="$(curl -s -o /dev/null -w "%{http_code}" "$OS_URL/$INDEX_NAME")"
if [ "$EXISTS_HTTP" = "200" ]; then
  if [ "$KEEP_INDEX" = "1" ]; then
    echo "Index $INDEX_NAME exists and KEEP_INDEX=1. Skipping delete/recreate."
  else
    echo "Index $INDEX_NAME exists. Deleting for fresh seed..."
    curl -fsS -XDELETE "$OS_URL/$INDEX_NAME" >/dev/null
  fi
fi

# Create index if missing (or after delete)
EXISTS_HTTP="$(curl -s -o /dev/null -w "%{http_code}" "$OS_URL/$INDEX_NAME")"
if [ "$EXISTS_HTTP" != "200" ]; then
  echo "Creating index $INDEX_NAME using mapping file."
  curl -fsS -XPUT "$OS_URL/$INDEX_NAME" \
    -H "Content-Type: application/json" \
    --data-binary @"$MAPPING_FILE" >/dev/null
fi

# Build NDJSON bulk body (5 docs)
NDJSON="$(cat <<'EOF'
{ "index": { "_index": "books_v1", "_id": "b1" } }
{ "doc_id": "b1", "title": "해리포터와 마법사의 돌", "authors": ["J.K. Rowling"], "publisher": "문학수첩", "publication_year": 1999 }
{ "index": { "_index": "books_v1", "_id": "b2" } }
{ "doc_id": "b2", "title": "해리포터와 비밀의 방", "authors": ["J.K. Rowling"], "publisher": "문학수첩", "publication_year": 2000 }
{ "index": { "_index": "books_v1", "_id": "b3" } }
{ "doc_id": "b3", "title": "클린 코드", "authors": ["Robert C. Martin"], "publisher": "인사이트", "publication_year": 2013 }
{ "index": { "_index": "books_v1", "_id": "b4" } }
{ "doc_id": "b4", "title": "도메인 주도 설계", "authors": ["Eric Evans"], "publisher": "위키북스", "publication_year": 2011 }
{ "index": { "_index": "books_v1", "_id": "b5" } }
{ "doc_id": "b5", "title": "엘라스틱서치 실무", "authors": ["김OO"], "publisher": "한빛미디어", "publication_year": 2022 }
EOF
)"

# IMPORTANT: Bulk request MUST end with a newline
NDJSON="${NDJSON}"$'\n'

# Ensure INDEX_NAME is used consistently in bulk actions even if changed
NDJSON="${NDJSON//\"books_v1\"/\"$INDEX_NAME\"}"

echo "Bulk indexing sample documents..."
BULK_RES="$(curl -sS -XPOST "$OS_URL/_bulk" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary "$NDJSON")"

# Fail if bulk had errors
echo "$BULK_RES" | grep -q '"errors":false' || {
  echo "Bulk indexing failed (errors=true). Response:"
  echo "$BULK_RES"
  exit 1
}

echo "Refreshing index."
curl -fsS -XPOST "$OS_URL/$INDEX_NAME/_refresh" >/dev/null

echo "Smoke check (count)."

if command -v python3 >/dev/null 2>&1; then
  COUNT="$(curl -sS "$OS_URL/$INDEX_NAME/_count" | python3 -c "import sys, json; print(json.load(sys.stdin).get('count',0))")"
elif command -v python >/dev/null 2>&1; then
  COUNT="$(curl -sS "$OS_URL/$INDEX_NAME/_count" | python -c "import sys, json; print(json.load(sys.stdin).get('count',0))")"
else
  COUNT="$(curl -sS "$OS_URL/$INDEX_NAME/_count" | tr -d '\n' | sed -E 's/.*"count"[[:space:]]*:[[:space:]]*([0-9]+).*/\1/')"
fi

if [ -z "${COUNT:-}" ] || [ "$COUNT" -lt 1 ]; then
  echo "Smoke failed: count='$COUNT'"
  curl -sS "$OS_URL/$INDEX_NAME/_count?pretty" || true
  exit 1
fi

echo "Smoke OK: count=$COUNT"

echo "Optional smoke query (title match '해리') (non-blocking)."
curl -sS -XPOST "$OS_URL/$INDEX_NAME/_search" \
  -H "Content-Type: application/json" \
  -d '{"query":{"match":{"title":"해리"}},"size":1}' | head -c 400 || true
echo
