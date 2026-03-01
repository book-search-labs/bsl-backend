#!/usr/bin/env bash
set -euo pipefail

OS_URL="${OS_URL:-http://localhost:9200}"
DOC_INDEX="${DOC_INDEX:-books_doc_v2_20260228_001}"
VEC_INDEX="${VEC_INDEX:-books_vec_v5_20260228_001}"
AC_INDEX="${AC_INDEX:-ac_candidates_v2_20260228_001}"
KEEP_INDEX="${KEEP_INDEX:-0}"
ADD_LEGACY_AC_ALIASES="${ADD_LEGACY_AC_ALIASES:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOC_MAPPING_FILE="$ROOT_DIR/infra/opensearch/books_doc_v2.mapping.json"
VEC_MAPPING_FILE="$ROOT_DIR/infra/opensearch/books_vec_v5.mapping.json"
AC_MAPPING_FILE="$ROOT_DIR/infra/opensearch/ac_candidates_v2.mapping.json"

for path in "$DOC_MAPPING_FILE" "$VEC_MAPPING_FILE" "$AC_MAPPING_FILE"; do
  if [ ! -f "$path" ]; then
    echo "Mapping file not found: $path" >&2
    exit 1
  fi
done

render_vector_mapping() {
  local src="$1"
  local dest="$2"
  python - "$src" "$dest" <<'PY'
import json
import os
import sys

src = sys.argv[1]
dest = sys.argv[2]
with open(src, "r", encoding="utf-8") as handle:
    data = json.load(handle)

embedding = data.get("mappings", {}).get("properties", {}).get("embedding", {})
method = embedding.get("method", {})
params = method.get("parameters", {})

if os.getenv("VEC_DIM"):
    embedding["dimension"] = int(os.getenv("VEC_DIM"))
if os.getenv("VEC_SPACE_TYPE"):
    method["space_type"] = os.getenv("VEC_SPACE_TYPE")
if os.getenv("VEC_HNSW_M"):
    params["m"] = int(os.getenv("VEC_HNSW_M"))
if os.getenv("VEC_HNSW_EF_CONSTRUCTION"):
    params["ef_construction"] = int(os.getenv("VEC_HNSW_EF_CONSTRUCTION"))
if params:
    method["parameters"] = params
if method:
    embedding["method"] = method
if embedding:
    data["mappings"]["properties"]["embedding"] = embedding

if os.getenv("VEC_HNSW_EF_SEARCH"):
    data.setdefault("settings", {}).setdefault("index", {})["knn.algo_param.ef_search"] = int(
        os.getenv("VEC_HNSW_EF_SEARCH")
    )

with open(dest, "w", encoding="utf-8") as handle:
    json.dump(data, handle)
PY
}

VEC_MAPPING_PAYLOAD="$VEC_MAPPING_FILE"
if [ -n "${VEC_DIM:-}" ] || [ -n "${VEC_SPACE_TYPE:-}" ] || [ -n "${VEC_HNSW_M:-}" ] || [ -n "${VEC_HNSW_EF_CONSTRUCTION:-}" ] || [ -n "${VEC_HNSW_EF_SEARCH:-}" ]; then
  VEC_MAPPING_PAYLOAD="$(mktemp)"
  render_vector_mapping "$VEC_MAPPING_FILE" "$VEC_MAPPING_PAYLOAD"
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

create_index() {
  local index_name="$1"
  local mapping_file="$2"
  local response_file
  local status
  echo "Creating index: $index_name"
  response_file="$(mktemp)"
  status="$(curl -sS -o "$response_file" -w "%{http_code}" -XPUT "$OS_URL/$index_name" \
    -H "Content-Type: application/json" \
    --data-binary "@$mapping_file")"
  if [ "$status" -ge 200 ] && [ "$status" -lt 300 ]; then
    rm -f "$response_file"
    return 0
  fi
  echo "Failed to create index $index_name (HTTP $status). Response:"
  cat "$response_file"
  rm -f "$response_file"
  return 1
}

delete_index() {
  local index_name="$1"
  echo "Deleting index: $index_name"
  curl -fsS -XDELETE "$OS_URL/$index_name" >/dev/null
}

prepare_index() {
  local index_name="$1"
  local mapping_file="$2"
  if index_exists "$index_name"; then
    if [ "$KEEP_INDEX" = "1" ]; then
      echo "Index $index_name exists and KEEP_INDEX=1. Skipping delete/recreate."
      return 0
    fi
    delete_index "$index_name"
  fi
  create_index "$index_name" "$mapping_file"
}

prepare_index "$DOC_INDEX" "$DOC_MAPPING_FILE"
prepare_index "$VEC_INDEX" "$VEC_MAPPING_PAYLOAD"
prepare_index "$AC_INDEX" "$AC_MAPPING_FILE"

alias_exists() {
  local alias_name="$1"
  local code
  code="$(curl -s -o /dev/null -w "%{http_code}" "$OS_URL/_alias/$alias_name")"
  [ "$code" = "200" ]
}

remove_alias() {
  local alias_name="$1"
  local index_pattern="$2"
  if alias_exists "$alias_name"; then
    curl -fsS -XPOST "$OS_URL/_aliases" \
      -H "Content-Type: application/json" \
      -d "{\"actions\":[{\"remove\":{\"index\":\"$index_pattern\",\"alias\":\"$alias_name\"}}]}" >/dev/null
  fi
}

add_alias() {
  local index_name="$1"
  local alias_name="$2"
  local is_write="${3:-0}"
  if [ "$is_write" = "1" ]; then
    curl -fsS -XPOST "$OS_URL/_aliases" \
      -H "Content-Type: application/json" \
      -d "{\"actions\":[{\"add\":{\"index\":\"$index_name\",\"alias\":\"$alias_name\",\"is_write_index\":true}}]}" >/dev/null
  else
    curl -fsS -XPOST "$OS_URL/_aliases" \
      -H "Content-Type: application/json" \
      -d "{\"actions\":[{\"add\":{\"index\":\"$index_name\",\"alias\":\"$alias_name\"}}]}" >/dev/null
  fi
}

echo "Updating aliases"
remove_alias "books_doc_read" "books_doc_v*"
remove_alias "books_doc_write" "books_doc_v*"
remove_alias "books_vec_read" "books_vec_v*"
remove_alias "books_vec_write" "books_vec_v*"
remove_alias "ac_candidates_read" "ac_candidates_v*"
remove_alias "ac_candidates_write" "ac_candidates_v*"
if [ "$ADD_LEGACY_AC_ALIASES" = "1" ]; then
  remove_alias "ac_read" "ac_candidates_v*"
  remove_alias "ac_write" "ac_candidates_v*"
fi

add_alias "$DOC_INDEX" "books_doc_read"
add_alias "$DOC_INDEX" "books_doc_write" "1"
add_alias "$VEC_INDEX" "books_vec_read"
add_alias "$VEC_INDEX" "books_vec_write" "1"
add_alias "$AC_INDEX" "ac_candidates_read"
add_alias "$AC_INDEX" "ac_candidates_write" "1"
if [ "$ADD_LEGACY_AC_ALIASES" = "1" ]; then
  add_alias "$AC_INDEX" "ac_read"
  add_alias "$AC_INDEX" "ac_write" "1"
fi

echo "Bootstrap complete."
