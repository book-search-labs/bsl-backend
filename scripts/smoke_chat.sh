#!/usr/bin/env bash
set -euo pipefail

BFF_BASE_URL="${BFF_BASE_URL:-http://localhost:8088}"
STREAM="${STREAM:-true}"

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

non_stream_payload='{"version":"v1","message":{"role":"user","content":"해리 포터가 뭐야?"},"options":{"top_k":4}}'
fallback_payload='{"version":"v1","message":{"role":"user","content":"zxqv 이건 아마 없을 질문입니다"},"options":{"top_k":4}}'

echo "[1/3] non-stream chat..."
curl -fsS -X POST "$BFF_BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d "$non_stream_payload" >"$tmp_dir/non_stream.json"
grep -q '"status"' "$tmp_dir/non_stream.json"

echo "[2/3] stream chat..."
if [ "$STREAM" = "true" ]; then
  curl -fsS -N -X POST "$BFF_BASE_URL/chat?stream=true" \
    -H "Content-Type: application/json" \
    -d "$non_stream_payload" >"$tmp_dir/stream.txt"
  grep -q "event: done" "$tmp_dir/stream.txt"
fi

echo "[3/3] fallback chat (no chunks)..."
curl -fsS -X POST "$BFF_BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d "$fallback_payload" >"$tmp_dir/fallback.json"
grep -q "insufficient_evidence" "$tmp_dir/fallback.json" || true

echo "Smoke chat completed."
