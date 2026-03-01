#!/usr/bin/env bash
set -euo pipefail

OS_URL="${OS_URL:-http://localhost:9200}"
DOC_INDEX="${DOC_INDEX:-books_doc_v2_1_20260301_001}"
VEC_INDEX="${VEC_INDEX:-books_vec_v5_20260228_001}"
CHUNK_INDEX="${CHUNK_INDEX:-book_chunks_v1}"
DOCS_DOC_INDEX="${DOCS_DOC_INDEX:-docs_doc_v1_20260116_001}"
DOCS_VEC_INDEX="${DOCS_VEC_INDEX:-docs_vec_v2_20260228_001}"
AC_INDEX="${AC_INDEX:-ac_candidates_v2_20260228_001}"
AUTHORS_INDEX="${AUTHORS_INDEX:-authors_doc_v1_20260116_001}"
SERIES_INDEX="${SERIES_INDEX:-series_doc_v1_20260116_001}"
KEEP_INDEX="${KEEP_INDEX:-0}"
ENABLE_ENTITY_INDICES="${ENABLE_ENTITY_INDICES:-1}"
ENABLE_CHUNK_INDEX="${ENABLE_CHUNK_INDEX:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOC_MAPPING_FILE="${DOC_MAPPING_FILE:-$ROOT_DIR/infra/opensearch/books_doc_v2_1.mapping.json}"
VEC_MAPPING_FILE="$ROOT_DIR/infra/opensearch/books_vec_v5.mapping.json"
CHUNK_MAPPING_FILE="$ROOT_DIR/infra/opensearch/book_chunks_v1.mapping.json"
DOCS_DOC_MAPPING_FILE="$ROOT_DIR/infra/opensearch/docs_doc_v1.mapping.json"
DOCS_VEC_MAPPING_FILE="$ROOT_DIR/infra/opensearch/docs_vec_v2.mapping.json"
AC_MAPPING_FILE="$ROOT_DIR/infra/opensearch/ac_candidates_v2.mapping.json"
AUTHORS_MAPPING_FILE="$ROOT_DIR/infra/opensearch/authors_doc_v1.mapping.json"
AUTHORS_MAPPING_FALLBACK_FILE="$ROOT_DIR/infra/opensearch/authors_doc_v1.local.mapping.json"
SERIES_MAPPING_FILE="$ROOT_DIR/infra/opensearch/series_doc_v1.mapping.json"

if [ ! -f "$DOC_MAPPING_FILE" ]; then
  echo "Mapping file not found: $DOC_MAPPING_FILE" >&2
  exit 1
fi

if [ ! -f "$VEC_MAPPING_FILE" ]; then
  echo "Mapping file not found: $VEC_MAPPING_FILE" >&2
  exit 1
fi

if [ "$ENABLE_CHUNK_INDEX" = "1" ] && [ ! -f "$CHUNK_MAPPING_FILE" ]; then
  echo "Mapping file not found: $CHUNK_MAPPING_FILE" >&2
  exit 1
fi

if [ ! -f "$DOCS_DOC_MAPPING_FILE" ]; then
  echo "Mapping file not found: $DOCS_DOC_MAPPING_FILE" >&2
  exit 1
fi

if [ ! -f "$DOCS_VEC_MAPPING_FILE" ]; then
  echo "Mapping file not found: $DOCS_VEC_MAPPING_FILE" >&2
  exit 1
fi

if [ ! -f "$AC_MAPPING_FILE" ]; then
  echo "Mapping file not found: $AC_MAPPING_FILE" >&2
  exit 1
fi

if [ ! -f "$AUTHORS_MAPPING_FILE" ]; then
  echo "Mapping file not found: $AUTHORS_MAPPING_FILE" >&2
  exit 1
fi

if [ ! -f "$SERIES_MAPPING_FILE" ]; then
  echo "Mapping file not found: $SERIES_MAPPING_FILE" >&2
  exit 1
fi

render_mapping() {
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

dim = os.getenv("VEC_DIM")
space = os.getenv("VEC_SPACE_TYPE")
m = os.getenv("VEC_HNSW_M")
efc = os.getenv("VEC_HNSW_EF_CONSTRUCTION")
efs = os.getenv("VEC_HNSW_EF_SEARCH")

embedding = data.get("mappings", {}).get("properties", {}).get("embedding", {})
method = embedding.get("method", {})
params = method.get("parameters", {})

if dim:
    embedding["dimension"] = int(dim)
if space:
    method["space_type"] = space
if m:
    params["m"] = int(m)
if efc:
    params["ef_construction"] = int(efc)
if params:
    method["parameters"] = params
if method:
    embedding["method"] = method
if embedding:
    data["mappings"]["properties"]["embedding"] = embedding
if efs:
    data.setdefault("settings", {}).setdefault("index", {})["knn.algo_param.ef_search"] = int(efs)

with open(dest, "w", encoding="utf-8") as handle:
    json.dump(data, handle)
PY
}

VEC_MAPPING_PAYLOAD="$VEC_MAPPING_FILE"
CHUNK_MAPPING_PAYLOAD="$CHUNK_MAPPING_FILE"
DOCS_VEC_MAPPING_PAYLOAD="$DOCS_VEC_MAPPING_FILE"

if [ -n "${VEC_DIM:-}" ] || [ -n "${VEC_SPACE_TYPE:-}" ] || [ -n "${VEC_HNSW_M:-}" ] || [ -n "${VEC_HNSW_EF_CONSTRUCTION:-}" ] || [ -n "${VEC_HNSW_EF_SEARCH:-}" ]; then
  VEC_MAPPING_PAYLOAD="$(mktemp)"
  render_mapping "$VEC_MAPPING_FILE" "$VEC_MAPPING_PAYLOAD"
  DOCS_VEC_MAPPING_PAYLOAD="$(mktemp)"
  render_mapping "$DOCS_VEC_MAPPING_FILE" "$DOCS_VEC_MAPPING_PAYLOAD"
  if [ "$ENABLE_CHUNK_INDEX" = "1" ] && [ -f "$CHUNK_MAPPING_FILE" ]; then
    CHUNK_MAPPING_PAYLOAD="$(mktemp)"
    render_mapping "$CHUNK_MAPPING_FILE" "$CHUNK_MAPPING_PAYLOAD"
  fi
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

plugins="$(curl -fsS "$OS_URL/_cat/plugins?h=component" || true)"
if ! printf '%s\n' "$plugins" | grep -qx "analysis-nori"; then
  echo "Missing OpenSearch plugin: analysis-nori" >&2
  echo "Rebuild opensearch image with infra/docker/opensearch/Dockerfile and restart." >&2
  exit 1
fi
if ! printf '%s\n' "$plugins" | grep -qx "analysis-icu"; then
  echo "Missing OpenSearch plugin: analysis-icu" >&2
  echo "Rebuild opensearch image with infra/docker/opensearch/Dockerfile and restart." >&2
  exit 1
fi

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
  create_index "$VEC_INDEX" "$VEC_MAPPING_PAYLOAD"
fi

if [ "$ENABLE_CHUNK_INDEX" = "1" ]; then
  if index_exists "$CHUNK_INDEX"; then
    if [ "$KEEP_INDEX" = "1" ]; then
      echo "Index $CHUNK_INDEX exists and KEEP_INDEX=1. Skipping delete/recreate."
    else
      delete_index "$CHUNK_INDEX"
    fi
  fi

  if ! index_exists "$CHUNK_INDEX"; then
    create_index "$CHUNK_INDEX" "$CHUNK_MAPPING_PAYLOAD" || {
      echo "Skipping chunk index (optional)."
    }
  fi
else
  echo "ENABLE_CHUNK_INDEX=0; skipping chunk index."
fi

if index_exists "$DOCS_DOC_INDEX"; then
  if [ "$KEEP_INDEX" = "1" ]; then
    echo "Index $DOCS_DOC_INDEX exists and KEEP_INDEX=1. Skipping delete/recreate."
  else
    delete_index "$DOCS_DOC_INDEX"
  fi
fi

if ! index_exists "$DOCS_DOC_INDEX"; then
  create_index "$DOCS_DOC_INDEX" "$DOCS_DOC_MAPPING_FILE"
fi

if index_exists "$DOCS_VEC_INDEX"; then
  if [ "$KEEP_INDEX" = "1" ]; then
    echo "Index $DOCS_VEC_INDEX exists and KEEP_INDEX=1. Skipping delete/recreate."
  else
    delete_index "$DOCS_VEC_INDEX"
  fi
fi

if ! index_exists "$DOCS_VEC_INDEX"; then
  create_index "$DOCS_VEC_INDEX" "$DOCS_VEC_MAPPING_PAYLOAD"
fi

if index_exists "$AC_INDEX"; then
  if [ "$KEEP_INDEX" = "1" ]; then
    echo "Index $AC_INDEX exists and KEEP_INDEX=1. Skipping delete/recreate."
  else
    delete_index "$AC_INDEX"
  fi
fi

if ! index_exists "$AC_INDEX"; then
  create_index "$AC_INDEX" "$AC_MAPPING_FILE" || exit 1
fi

if [ "$ENABLE_ENTITY_INDICES" = "1" ]; then
  if index_exists "$AUTHORS_INDEX"; then
    if [ "$KEEP_INDEX" = "1" ]; then
      echo "Index $AUTHORS_INDEX exists and KEEP_INDEX=1. Skipping delete/recreate."
    else
      delete_index "$AUTHORS_INDEX"
    fi
  fi

  if ! index_exists "$AUTHORS_INDEX"; then
    if ! create_index "$AUTHORS_INDEX" "$AUTHORS_MAPPING_FILE"; then
      if [ -f "$AUTHORS_MAPPING_FALLBACK_FILE" ]; then
        echo "Retrying authors index with fallback mapping."
        create_index "$AUTHORS_INDEX" "$AUTHORS_MAPPING_FALLBACK_FILE" || {
          echo "Skipping authors index (optional)."
        }
      else
        echo "Skipping authors index (optional)."
      fi
    fi
  fi

  if index_exists "$SERIES_INDEX"; then
    if [ "$KEEP_INDEX" = "1" ]; then
      echo "Index $SERIES_INDEX exists and KEEP_INDEX=1. Skipping delete/recreate."
    else
      delete_index "$SERIES_INDEX"
    fi
  fi

  if ! index_exists "$SERIES_INDEX"; then
    if ! create_index "$SERIES_INDEX" "$SERIES_MAPPING_FILE"; then
      echo "Skipping series index (optional)."
    fi
  fi
else
  echo "ENABLE_ENTITY_INDICES=0; skipping authors/series indices."
fi

echo "Updating aliases (doc/vec/docs/ac/authors/series read/write)"

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
  if ! index_exists "$index_name"; then
    echo "Skipping alias $alias_name (missing index $index_name)."
    return 0
  fi
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

remove_alias "books_doc_read" "books_doc_v*"
remove_alias "books_doc_write" "books_doc_v*"
remove_alias "books_vec_read" "books_vec_v*"
remove_alias "books_vec_write" "books_vec_v*"
remove_alias "docs_doc_read" "docs_doc_v*"
remove_alias "docs_doc_write" "docs_doc_v*"
remove_alias "docs_vec_read" "docs_vec_v*"
remove_alias "docs_vec_write" "docs_vec_v*"
remove_alias "ac_read" "ac_candidates_v*"
remove_alias "ac_write" "ac_candidates_v*"
remove_alias "ac_candidates_read" "ac_candidates_v*"
remove_alias "ac_candidates_write" "ac_candidates_v*"
remove_alias "authors_doc_read" "authors_doc_v1_*"
remove_alias "authors_doc_write" "authors_doc_v1_*"
remove_alias "series_doc_read" "series_doc_v1_*"
remove_alias "series_doc_write" "series_doc_v1_*"

add_alias "$DOC_INDEX" "books_doc_read"
add_alias "$DOC_INDEX" "books_doc_write" "1"
add_alias "$VEC_INDEX" "books_vec_read"
add_alias "$VEC_INDEX" "books_vec_write" "1"
add_alias "$DOCS_DOC_INDEX" "docs_doc_read"
add_alias "$DOCS_DOC_INDEX" "docs_doc_write" "1"
add_alias "$DOCS_VEC_INDEX" "docs_vec_read"
add_alias "$DOCS_VEC_INDEX" "docs_vec_write" "1"
add_alias "$AC_INDEX" "ac_read"
add_alias "$AC_INDEX" "ac_write" "1"
add_alias "$AC_INDEX" "ac_candidates_read"
add_alias "$AC_INDEX" "ac_candidates_write" "1"
add_alias "$AUTHORS_INDEX" "authors_doc_read"
add_alias "$AUTHORS_INDEX" "authors_doc_write" "1"
add_alias "$SERIES_INDEX" "series_doc_read"
add_alias "$SERIES_INDEX" "series_doc_write" "1"

echo "Bootstrap complete."
