#!/usr/bin/env bash
set -euo pipefail

OS_URL="${OS_URL:-http://localhost:9200}"
SRC_INDEX="${SRC_INDEX:-books_doc_v2_20260228_001}"
DST_INDEX="${DST_INDEX:-books_doc_v2_1_20260301_001}"
DST_READ_ALIAS="${DST_READ_ALIAS:-books_doc_read}"
DST_WRITE_ALIAS="${DST_WRITE_ALIAS:-books_doc_write}"
CUTOVER_ALIASES="${CUTOVER_ALIASES:-0}"

echo "[books-doc-reindex-v2_1] OS_URL=$OS_URL"
echo "[books-doc-reindex-v2_1] SRC_INDEX=$SRC_INDEX"
echo "[books-doc-reindex-v2_1] DST_INDEX=$DST_INDEX"
echo "[books-doc-reindex-v2_1] CUTOVER_ALIASES=$CUTOVER_ALIASES"

for i in $(seq 1 30); do
  if curl -fsS "$OS_URL" >/dev/null 2>&1; then
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "OpenSearch not reachable at $OS_URL" >&2
    exit 1
  fi
  sleep 1
done

index_exists() {
  local index_name="$1"
  local code
  code="$(curl -s -o /dev/null -w "%{http_code}" "$OS_URL/$index_name")"
  [ "$code" = "200" ]
}

if ! index_exists "$SRC_INDEX"; then
  echo "Source index not found: $SRC_INDEX" >&2
  exit 1
fi

if ! index_exists "$DST_INDEX"; then
  echo "Destination index not found: $DST_INDEX" >&2
  exit 1
fi

REINDEX_BODY_FILE="$(mktemp)"
cat > "$REINDEX_BODY_FILE" <<JSON
{
  "source": { "index": "$SRC_INDEX" },
  "dest": { "index": "$DST_INDEX" },
  "script": {
    "lang": "painless",
    "source": "if (!ctx._source.containsKey('is_hidden') || ctx._source.is_hidden == null) { ctx._source.is_hidden = false; } if (ctx._source.containsKey('authors') && ctx._source.authors != null) { def ko = new ArrayList(); def en = new ArrayList(); for (def a : ctx._source.authors) { if (a == null) continue; if (a.containsKey('name_ko') && a.name_ko != null) { def n = a.name_ko.toString().trim(); if (!n.isEmpty() && !ko.contains(n)) { ko.add(n); } } if (a.containsKey('name_en') && a.name_en != null) { def n2 = a.name_en.toString().trim(); if (!n2.isEmpty() && !en.contains(n2)) { en.add(n2); } } } if (!ko.isEmpty()) { ctx._source.author_names_ko = ko; } if (!en.isEmpty()) { ctx._source.author_names_en = en; } }"
  }
}
JSON

echo "[books-doc-reindex-v2_1] running _reindex..."
curl -fsS -XPOST "$OS_URL/_reindex?wait_for_completion=true&refresh=true" \
  -H "Content-Type: application/json" \
  --data-binary "@$REINDEX_BODY_FILE" >/tmp/books_doc_reindex_v2_1_result.json
cat /tmp/books_doc_reindex_v2_1_result.json | jq '.total,.created,.updated,.failures'

echo "[books-doc-reindex-v2_1] validating is_hidden field..."
MISSING_HIDDEN_COUNT="$(curl -fsS -XPOST "$OS_URL/$DST_INDEX/_search" \
  -H "Content-Type: application/json" \
  -d '{"size":0,"query":{"bool":{"must_not":[{"exists":{"field":"is_hidden"}}]}}}' | jq -r '.hits.total.value')"
echo "[books-doc-reindex-v2_1] missing is_hidden docs: $MISSING_HIDDEN_COUNT"
if [ "$MISSING_HIDDEN_COUNT" != "0" ]; then
  echo "Validation failed: some docs are missing is_hidden" >&2
  exit 1
fi

echo "[books-doc-reindex-v2_1] validating author_names_ko/en backfill..."
MISSING_AUTHORS_FLAT="$(curl -fsS -XPOST "$OS_URL/$DST_INDEX/_search" \
  -H "Content-Type: application/json" \
  -d '{"size":0,"query":{"bool":{"filter":[{"exists":{"field":"authors"}},{"bool":{"must_not":[{"exists":{"field":"author_names_ko"}}]}}]}}}' | jq -r '.hits.total.value')"
echo "[books-doc-reindex-v2_1] docs with authors but missing author_names_ko: $MISSING_AUTHORS_FLAT"

if [ "$CUTOVER_ALIASES" = "1" ]; then
  echo "[books-doc-reindex-v2_1] cutting over aliases..."
  cat > /tmp/books_doc_alias_swap_v2_1.json <<JSON
{
  "actions": [
    { "remove": { "index": "books_doc_v*", "alias": "$DST_READ_ALIAS" } },
    { "remove": { "index": "books_doc_v*", "alias": "$DST_WRITE_ALIAS" } },
    { "add": { "index": "$DST_INDEX", "alias": "$DST_READ_ALIAS" } },
    { "add": { "index": "$DST_INDEX", "alias": "$DST_WRITE_ALIAS", "is_write_index": true } }
  ]
}
JSON
  curl -fsS -XPOST "$OS_URL/_aliases" \
    -H "Content-Type: application/json" \
    --data-binary @/tmp/books_doc_alias_swap_v2_1.json >/dev/null
  echo "[books-doc-reindex-v2_1] aliases updated."
fi

echo "[books-doc-reindex-v2_1] done."
