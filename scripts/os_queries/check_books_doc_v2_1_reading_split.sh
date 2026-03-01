#!/usr/bin/env bash
set -euo pipefail

OS_URL="${OS_URL:-http://localhost:9200}"
INDEX_ALIAS="${INDEX_ALIAS:-books_doc_read}"

LANG_KOR_URI="http://id.loc.gov/vocabulary/languages/kor"
LANG_KOR="kor"
LANG_KO="ko"

echo "[check] OS_URL=$OS_URL INDEX_ALIAS=$INDEX_ALIAS"

for i in $(seq 1 30); do
  if curl -fsS "$OS_URL" >/dev/null 2>&1; then
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "[fail] OpenSearch not reachable: $OS_URL" >&2
    exit 1
  fi
  sleep 1
done

alias_index="$(
  curl -fsS "$OS_URL/_cat/aliases?format=json" | jq -r \
    ".[] | select(.alias == \"$INDEX_ALIAS\") | .index" | head -n 1
)"

if [ -z "$alias_index" ]; then
  echo "[fail] alias not found: $INDEX_ALIAS" >&2
  exit 1
fi

if [[ "$alias_index" != books_doc_v2_1* ]]; then
  echo "[fail] alias $INDEX_ALIAS is not pointing to books_doc_v2_1*: $alias_index" >&2
  exit 1
fi
echo "[ok] alias target: $alias_index"

strict_tokens="$(
  curl -fsS -XPOST "$OS_URL/$alias_index/_analyze" \
    -H "Content-Type: application/json" \
    -d '{"analyzer":"ko_text_index","text":"茶的文化"}' | jq -r '.tokens[].token'
)"

if printf '%s\n' "$strict_tokens" | grep -qx '문화'; then
  echo "[fail] ko_text_index unexpectedly emits reading token '문화'" >&2
  exit 1
fi
echo "[ok] ko_text_index does not emit reading token"

reading_tokens="$(
  curl -fsS -XPOST "$OS_URL/$alias_index/_analyze" \
    -H "Content-Type: application/json" \
    -d '{"analyzer":"ko_text_reading_index","text":"茶的文化"}' | jq -r '.tokens[].token'
)"

if ! printf '%s\n' "$reading_tokens" | grep -qx '문화'; then
  echo "[fail] ko_text_reading_index does not emit expected reading token '문화'" >&2
  exit 1
fi
echo "[ok] ko_text_reading_index emits reading token"

strict_title_top="$(
  curl -fsS -XPOST "$OS_URL/$INDEX_ALIAS/_search" \
    -H "Content-Type: application/json" \
    -d "{
      \"size\": 1,
      \"_source\": [\"title_ko\", \"language_code\", \"doc_id\"],
      \"query\": {
        \"bool\": {
          \"filter\": [
            {\"term\": {\"is_hidden\": false}},
            {
              \"bool\": {
                \"should\": [
                  {\"term\": {\"language_code\": \"$LANG_KOR_URI\"}},
                  {\"term\": {\"language_code\": \"$LANG_KOR\"}},
                  {\"term\": {\"language_code\": \"$LANG_KO\"}}
                ],
                \"minimum_should_match\": 1
              }
            }
          ],
          \"must\": [
            {\"match\": {\"title_ko\": {\"query\": \"문화\"}}}
          ]
        }
      }
    }" | jq -r '.hits.hits[0]._source.title_ko // empty'
)"

if [ -z "$strict_title_top" ]; then
  echo "[fail] strict title match returned no result for query=문화" >&2
  exit 1
fi

if ! printf '%s\n' "$strict_title_top" | grep -q '[가-힣]'; then
  echo "[fail] strict top title is not Hangul: $strict_title_top" >&2
  exit 1
fi
echo "[ok] strict top title is Hangul-first: $strict_title_top"

reading_hit_count="$(
  curl -fsS -XPOST "$OS_URL/$INDEX_ALIAS/_search" \
    -H "Content-Type: application/json" \
    -d '{
      "size": 0,
      "query": {
        "bool": {
          "filter": [{"term": {"is_hidden": false}}],
          "must": [{"match": {"title_ko.reading": {"query": "문화"}}}]
        }
      }
    }' | jq -r '.hits.total.value'
)"

if [ "$reading_hit_count" -le 0 ]; then
  echo "[fail] reading fallback query returned 0 hits" >&2
  exit 1
fi
echo "[ok] reading fallback hit count: $reading_hit_count"

echo "[done] books_doc_v2_1 reading split checks passed."
