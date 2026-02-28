#!/usr/bin/env bash
set -euo pipefail

MIS_URL="${MIS_URL:-http://localhost:8005}"
MODEL="${MIS_EMBED_MODEL_ID:-bge-m3}"
EXPECTED_DIM="${EXPECTED_DIM:-1024}"

response="$(
  cat <<JSON | curl -sS -X POST "$MIS_URL/v1/embed" -H 'Content-Type: application/json' -d @-
{
  "version": "v1",
  "trace_id": "smoke-trace",
  "request_id": "smoke-request",
  "model": "$MODEL",
  "normalize": true,
  "texts": ["해리포터", "환불 조건 정리"]
}
JSON
)"

tmp="$(mktemp)"
printf '%s' "$response" > "$tmp"

python3 - "$EXPECTED_DIM" "$tmp" <<'PY'
import json
import sys

expected = int(sys.argv[1])
path = sys.argv[2]
with open(path, "r", encoding="utf-8") as handle:
    data = json.load(handle)
dim = int(data.get("dim") or 0)
vectors = data.get("vectors") or []

if dim != expected:
    raise SystemExit(f"[FAIL] dim mismatch: got={dim} expected={expected}")
if len(vectors) != 2:
    raise SystemExit(f"[FAIL] vector count mismatch: got={len(vectors)} expected=2")
for idx, vec in enumerate(vectors):
    if len(vec) != expected:
        raise SystemExit(
            f"[FAIL] vector[{idx}] dim mismatch: got={len(vec)} expected={expected}"
        )

print(
    json.dumps(
        {
            "status": "ok",
            "model": data.get("model"),
            "dim": dim,
            "count": len(vectors),
        },
        ensure_ascii=True,
    )
)
PY

rm -f "$tmp"
