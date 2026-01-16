#!/usr/bin/env bash
set -euo pipefail

OS_URL="${OS_URL:-http://localhost:9200}"
DOC_ALIAS="${DOC_ALIAS:-books_doc_write}"
VEC_ALIAS="${VEC_ALIAS:-books_vec_write}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
else
  echo "Python is required to generate deterministic vectors." >&2
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

vector_for_doc() {
  local doc_id="$1"
  "$PYTHON" - "$doc_id" <<'PY'
import sys
import hashlib
import json
import random

doc_id = sys.argv[1]
seed = int(hashlib.sha256(doc_id.encode("utf-8")).hexdigest()[:8], 16)
rng = random.Random(seed)
vec = [round(rng.random(), 6) for _ in range(1024)]
print(json.dumps(vec))
PY
}

UPDATED_AT="2026-01-16T00:00:00Z"

vec_b1="$(vector_for_doc "b1")"
vec_b2="$(vector_for_doc "b2")"
vec_b3="$(vector_for_doc "b3")"
vec_b4="$(vector_for_doc "b4")"
vec_b5="$(vector_for_doc "b5")"

DOC_BULK="$(cat <<'DOC_EOF'
{ "index": { "_index": "__DOC_ALIAS__", "_id": "b1" } }
{ "doc_id": "b1", "title_ko": "해리 포터와 마법사의 돌", "title_en": "Harry Potter and the Philosopher's Stone", "authors": [{ "agent_id": "a1", "name_ko": "J.K. 롤링", "name_en": "J.K. Rowling", "role": "author", "ord": 1 }], "publisher_name": "문학수첩", "identifiers": { "isbn13": "9788983920772" }, "language_code": "ko", "issued_year": 1999, "volume": 1, "edition_labels": ["recover"], "category_paths": ["books>fiction>fantasy"], "concept_ids": ["c_fantasy", "c_magic"], "is_hidden": false, "updated_at": "__UPDATED_AT__" }
{ "index": { "_index": "__DOC_ALIAS__", "_id": "b2" } }
{ "doc_id": "b2", "title_ko": "해리 포터와 비밀의 방", "title_en": "Harry Potter and the Chamber of Secrets", "authors": [{ "agent_id": "a1", "name_ko": "J.K. 롤링", "name_en": "J.K. Rowling", "role": "author", "ord": 1 }], "publisher_name": "문학수첩", "identifiers": { "isbn13": "9788983920789" }, "language_code": "ko", "issued_year": 2000, "volume": 2, "edition_labels": [], "category_paths": ["books>fiction>fantasy"], "concept_ids": ["c_fantasy", "c_wizard"], "is_hidden": false, "updated_at": "__UPDATED_AT__" }
{ "index": { "_index": "__DOC_ALIAS__", "_id": "b3" } }
{ "doc_id": "b3", "title_ko": "클린 코드", "title_en": "Clean Code", "authors": [{ "agent_id": "a2", "name_ko": "로버트 C. 마틴", "name_en": "Robert C. Martin", "role": "author", "ord": 1 }], "publisher_name": "인사이트", "identifiers": { "isbn13": "9788966260959" }, "language_code": "ko", "issued_year": 2013, "edition_labels": [], "category_paths": ["books>software>engineering"], "concept_ids": ["c_clean_code", "c_quality"], "is_hidden": false, "updated_at": "__UPDATED_AT__" }
{ "index": { "_index": "__DOC_ALIAS__", "_id": "b4" } }
{ "doc_id": "b4", "title_ko": "도메인 주도 설계", "title_en": "Domain-Driven Design", "authors": [{ "agent_id": "a3", "name_ko": "에릭 에반스", "name_en": "Eric Evans", "role": "author", "ord": 1 }], "publisher_name": "위키북스", "identifiers": { "isbn13": "9788992939278" }, "language_code": "ko", "issued_year": 2011, "edition_labels": [], "category_paths": ["books>software>architecture"], "concept_ids": ["c_domain_driven", "c_design"], "is_hidden": false, "updated_at": "__UPDATED_AT__" }
{ "index": { "_index": "__DOC_ALIAS__", "_id": "b5" } }
{ "doc_id": "b5", "title_ko": "엘라스틱서치 실무", "title_en": "Elasticsearch in Practice", "authors": [{ "agent_id": "a4", "name_ko": "김OO", "name_en": "Kim", "role": "author", "ord": 1 }], "publisher_name": "한빛미디어", "identifiers": { "isbn13": "9788968481239" }, "language_code": "ko", "issued_year": 2022, "edition_labels": [], "category_paths": ["books>software>search"], "concept_ids": ["c_search", "c_opensearch"], "is_hidden": false, "updated_at": "__UPDATED_AT__" }
DOC_EOF
)"

DOC_BULK="${DOC_BULK//__DOC_ALIAS__/$DOC_ALIAS}"
DOC_BULK="${DOC_BULK//__UPDATED_AT__/$UPDATED_AT}"
DOC_BULK="${DOC_BULK}"$'\n'

echo "Bulk indexing doc index..."
DOC_RES="$(curl -sS -XPOST "$OS_URL/_bulk" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary "$DOC_BULK")"

echo "$DOC_RES" | grep -q '"errors":false' || {
  echo "Doc bulk indexing failed (errors=true). Response:" >&2
  echo "$DOC_RES" >&2
  exit 1
}

VEC_BULK="$(cat <<'VEC_EOF'
{ "index": { "_index": "__VEC_ALIAS__", "_id": "b1" } }
{ "doc_id": "b1", "language_code": "ko", "category_paths": ["books>fiction>fantasy"], "concept_ids": ["c_fantasy", "c_magic"], "embedding": __VEC_B1__, "updated_at": "__UPDATED_AT__" }
{ "index": { "_index": "__VEC_ALIAS__", "_id": "b2" } }
{ "doc_id": "b2", "language_code": "ko", "category_paths": ["books>fiction>fantasy"], "concept_ids": ["c_fantasy", "c_wizard"], "embedding": __VEC_B2__, "updated_at": "__UPDATED_AT__" }
{ "index": { "_index": "__VEC_ALIAS__", "_id": "b3" } }
{ "doc_id": "b3", "language_code": "ko", "category_paths": ["books>software>engineering"], "concept_ids": ["c_clean_code", "c_quality"], "embedding": __VEC_B3__, "updated_at": "__UPDATED_AT__" }
{ "index": { "_index": "__VEC_ALIAS__", "_id": "b4" } }
{ "doc_id": "b4", "language_code": "ko", "category_paths": ["books>software>architecture"], "concept_ids": ["c_domain_driven", "c_design"], "embedding": __VEC_B4__, "updated_at": "__UPDATED_AT__" }
{ "index": { "_index": "__VEC_ALIAS__", "_id": "b5" } }
{ "doc_id": "b5", "language_code": "ko", "category_paths": ["books>software>search"], "concept_ids": ["c_search", "c_opensearch"], "embedding": __VEC_B5__, "updated_at": "__UPDATED_AT__" }
VEC_EOF
)"

VEC_BULK="${VEC_BULK//__VEC_ALIAS__/$VEC_ALIAS}"
VEC_BULK="${VEC_BULK//__UPDATED_AT__/$UPDATED_AT}"
VEC_BULK="${VEC_BULK//__VEC_B1__/$vec_b1}"
VEC_BULK="${VEC_BULK//__VEC_B2__/$vec_b2}"
VEC_BULK="${VEC_BULK//__VEC_B3__/$vec_b3}"
VEC_BULK="${VEC_BULK//__VEC_B4__/$vec_b4}"
VEC_BULK="${VEC_BULK//__VEC_B5__/$vec_b5}"
VEC_BULK="${VEC_BULK}"$'\n'

echo "Bulk indexing vec index..."
VEC_RES="$(curl -sS -XPOST "$OS_URL/_bulk" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary "$VEC_BULK")"

echo "$VEC_RES" | grep -q '"errors":false' || {
  echo "Vec bulk indexing failed (errors=true). Response:" >&2
  echo "$VEC_RES" >&2
  exit 1
}

echo "Refreshing indices..."
curl -fsS -XPOST "$OS_URL/$DOC_ALIAS/_refresh" >/dev/null
curl -fsS -XPOST "$OS_URL/$VEC_ALIAS/_refresh" >/dev/null

extract_hits() {
  "$PYTHON" -c 'import json, sys; data=json.load(sys.stdin); value=data.get("hits", {}).get("total", 0); print(value.get("value", 0) if isinstance(value, dict) else value)'
}

echo "Running lexical smoke check (title_ko match: 해리)..."
LEX_RES="$(curl -sS -XPOST "$OS_URL/books_doc_read/_search" \
  -H "Content-Type: application/json" \
  -d '{"query":{"match":{"title_ko":"해리"}},"size":3}')"

LEX_HITS="$(printf '%s' "$LEX_RES" | extract_hits)"
if [ -z "$LEX_HITS" ] || [ "$LEX_HITS" -lt 1 ]; then
  echo "Lexical smoke failed: hits=$LEX_HITS" >&2
  echo "$LEX_RES" >&2
  exit 1
fi

echo "OK: lexical hits=$LEX_HITS"

QUERY_VECTOR="$vec_b1"

echo "Running vector smoke check (knn on embedding)..."
KNN_RES="$(curl -sS -XPOST "$OS_URL/books_vec_read/_search" \
  -H "Content-Type: application/json" \
  -d "{\"size\":3,\"query\":{\"knn\":{\"embedding\":{\"vector\":$QUERY_VECTOR,\"k\":3}}}}")"

KNN_HITS="$(printf '%s' "$KNN_RES" | extract_hits)"
if [ -z "$KNN_HITS" ] || [ "$KNN_HITS" -lt 1 ]; then
  echo "Vector smoke failed: hits=$KNN_HITS" >&2
  echo "$KNN_RES" >&2
  exit 1
fi

echo "OK: knn hits=$KNN_HITS"
