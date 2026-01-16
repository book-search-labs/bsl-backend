#!/usr/bin/env bash
set -euo pipefail

OS_URL="${OS_URL:-http://localhost:9200}"
DOC_INDEX="${DOC_INDEX:-books_doc_v1_20260116_001}"
VEC_INDEX="${VEC_INDEX:-books_vec_v1_20260116_001}"
KEEP_INDEX="${KEEP_INDEX:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOC_MAPPING_FILE="$ROOT_DIR/infra/opensearch/books_doc_v1.mapping.json"
VEC_MAPPING_FILE="$ROOT_DIR/infra/opensearch/books_vec_v1.mapping.json"

if [ ! -f "$DOC_MAPPING_FILE" ]; then
  echo "Mapping file not found: $DOC_MAPPING_FILE" >&2
  exit 1
fi

if [ ! -f "$VEC_MAPPING_FILE" ]; then
  echo "Mapping file not found: $VEC_MAPPING_FILE" >&2
  exit 1
fi

echo "OpenSearch URL: $OS_URL"

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

alias_exists() {
  local alias_name="$1"
  local code
  code="$(curl -s -o /dev/null -w "%{http_code}" "$OS_URL/_alias/$alias_name")"
  [ "$code" = "200" ]
}

create_index() {
  local index_name="$1"
  local mapping_file="$2"
  echo "Creating index: $index_name"
  curl -fsS -XPUT "$OS_URL/$index_name" \
    -H "Content-Type: application/json" \
    --data-binary "@$mapping_file" >/dev/null
}

delete_index() {
  local index_name="$1"
  echo "Deleting index: $index_name"
  curl -fsS -XDELETE "$OS_URL/$index_name" >/dev/null
}

if index_exists "$DOC_INDEX"; then
  if [ "$KEEP_INDEX" = "1" ]; then
    echo "Index $DOC_INDEX exists and KEEP_INDEX=1. Skipping delete/recreate."
  else
    delete_index "$DOC_INDEX"
  fi
fi

if ! index_exists "$DOC_INDEX"; then
  create_index "$DOC_INDEX" "$DOC_MAPPING_FILE"
fi

if index_exists "$VEC_INDEX"; then
  if [ "$KEEP_INDEX" = "1" ]; then
    echo "Index $VEC_INDEX exists and KEEP_INDEX=1. Skipping delete/recreate."
  else
    delete_index "$VEC_INDEX"
  fi
fi

if ! index_exists "$VEC_INDEX"; then
  create_index "$VEC_INDEX" "$VEC_MAPPING_FILE"
fi

echo "Updating aliases (doc/vec read/write)"

if alias_exists "books_doc_read"; then
  curl -fsS -XPOST "$OS_URL/_aliases" \
    -H "Content-Type: application/json" \
    -d "{\"actions\":[{\"remove\":{\"index\":\"books_doc_v1_*\",\"alias\":\"books_doc_read\"}}]}" >/dev/null
fi

if alias_exists "books_doc_write"; then
  curl -fsS -XPOST "$OS_URL/_aliases" \
    -H "Content-Type: application/json" \
    -d "{\"actions\":[{\"remove\":{\"index\":\"books_doc_v1_*\",\"alias\":\"books_doc_write\"}}]}" >/dev/null
fi

if alias_exists "books_vec_read"; then
  curl -fsS -XPOST "$OS_URL/_aliases" \
    -H "Content-Type: application/json" \
    -d "{\"actions\":[{\"remove\":{\"index\":\"books_vec_v1_*\",\"alias\":\"books_vec_read\"}}]}" >/dev/null
fi

if alias_exists "books_vec_write"; then
  curl -fsS -XPOST "$OS_URL/_aliases" \
    -H "Content-Type: application/json" \
    -d "{\"actions\":[{\"remove\":{\"index\":\"books_vec_v1_*\",\"alias\":\"books_vec_write\"}}]}" >/dev/null
fi

curl -fsS -XPOST "$OS_URL/_aliases" \
  -H "Content-Type: application/json" \
  -d "{\"actions\":[{\"add\":{\"index\":\"$DOC_INDEX\",\"alias\":\"books_doc_read\"}},{\"add\":{\"index\":\"$DOC_INDEX\",\"alias\":\"books_doc_write\",\"is_write_index\":true}},{\"add\":{\"index\":\"$VEC_INDEX\",\"alias\":\"books_vec_read\"}},{\"add\":{\"index\":\"$VEC_INDEX\",\"alias\":\"books_vec_write\",\"is_write_index\":true}}]}" >/dev/null

echo "Bootstrap complete."
