#!/usr/bin/env bash
set -euo pipefail

MIS_URL="${MIS_URL:-http://localhost:8005}"
QS_URL="${QS_URL:-http://localhost:8001}"
TEXT="${SPELL_TEXT:-정약    용  자서전 01권}"

if command -v jq >/dev/null 2>&1; then
  CURL_JQ="| jq"
else
  CURL_JQ=""
fi

echo "[MIS] /v1/spell"
cat <<JSON | curl -sS -X POST "$MIS_URL/v1/spell" -H 'Content-Type: application/json' -d @- ${CURL_JQ}
{
  "version": "v1",
  "trace_id": "trace_spell_smoke",
  "request_id": "req_spell_smoke",
  "text": "$TEXT",
  "locale": "ko-KR",
  "model": "t5-typo-ko-v1"
}
JSON

echo ""

echo "[QS] /query/enhance (SPELL_ONLY path)"
cat <<JSON | curl -sS -X POST "$QS_URL/query/enhance" -H 'Content-Type: application/json' -d @- ${CURL_JQ}
{
  "request_id": "req_spell_smoke_qs",
  "trace_id": "trace_spell_smoke_qs",
  "q_norm": "harry pottre",
  "q_nospace": "harrypottre",
  "detected": {"mode": "normal", "is_isbn": false, "has_volume": false, "lang": "en"},
  "reason": "HIGH_OOV",
  "signals": {"latency_budget_ms": 800}
}
JSON
