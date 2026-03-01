#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "[FAIL] python not found"
    exit 1
  fi
fi

FEEDBACK_JSONL="${CHAT_FEEDBACK_JSONL:-$ROOT_DIR/evaluation/chat/feedback.jsonl}"
FEEDBACK_SUMMARY="${CHAT_FEEDBACK_SUMMARY:-$ROOT_DIR/evaluation/chat/feedback_summary.json}"
FEEDBACK_BACKLOG="${CHAT_FEEDBACK_BACKLOG:-$ROOT_DIR/evaluation/chat/feedback_backlog.json}"
FEEDBACK_BACKLOG_MD="${CHAT_FEEDBACK_BACKLOG_MD:-$ROOT_DIR/tasks/backlog/generated/chat_feedback_auto.md}"
FEEDBACK_BACKLOG_TICKETS_DIR="${CHAT_FEEDBACK_BACKLOG_TICKETS_DIR:-$ROOT_DIR/tasks/backlog/generated/feedback}"
FEEDBACK_DAYS="${CHAT_FEEDBACK_DAYS:-7}"
FEEDBACK_SINCE="${CHAT_FEEDBACK_SINCE:-}"
FEEDBACK_INCLUDE_COMMENT="${CHAT_FEEDBACK_INCLUDE_COMMENT:-0}"

RECOMMEND_METRICS_URL="${CHAT_RECOMMEND_METRICS_URL:-http://localhost:8001/metrics}"
RECOMMEND_SESSION_ID="${CHAT_RECOMMEND_SESSION_ID:-u:101:default}"
RECOMMEND_REPORT_OUT="${CHAT_RECOMMEND_REPORT_OUT:-$ROOT_DIR/data/eval/reports}"
RECOMMEND_MIN_SAMPLES="${CHAT_RECOMMEND_MIN_SAMPLES:-20}"
RECOMMEND_MAX_BLOCK_RATE="${CHAT_RECOMMEND_MAX_BLOCK_RATE:-0.4}"
RECOMMEND_MAX_AUTO_DISABLE_TOTAL="${CHAT_RECOMMEND_MAX_AUTO_DISABLE_TOTAL:-0}"

echo "[1/3] export chat feedback outbox events"
EXPORT_ARGS=(
  "$ROOT_DIR/scripts/chat/export_feedback_events.py"
  --output "$FEEDBACK_JSONL"
  --days "$FEEDBACK_DAYS"
)
if [ -n "$FEEDBACK_SINCE" ]; then
  EXPORT_ARGS+=(--since "$FEEDBACK_SINCE")
fi
if [ "$FEEDBACK_INCLUDE_COMMENT" = "1" ]; then
  EXPORT_ARGS+=(--include-comment)
fi
"$PYTHON_BIN" "${EXPORT_ARGS[@]}"

echo "[2/3] aggregate feedback and generate backlog seeds"
"$PYTHON_BIN" "$ROOT_DIR/scripts/chat/aggregate_feedback.py" \
  --input "$FEEDBACK_JSONL" \
  --output "$FEEDBACK_SUMMARY" \
  --backlog-output "$FEEDBACK_BACKLOG" \
  --allow-empty

if [ -f "$FEEDBACK_BACKLOG" ]; then
  "$PYTHON_BIN" "$ROOT_DIR/scripts/chat/render_feedback_backlog_md.py" \
    --input "$FEEDBACK_BACKLOG" \
    --output "$FEEDBACK_BACKLOG_MD"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/chat/sync_feedback_backlog_tickets.py" \
    --input "$FEEDBACK_BACKLOG" \
    --output-dir "$FEEDBACK_BACKLOG_TICKETS_DIR"
fi

echo "[3/3] generate recommendation quality report"
if command -v curl >/dev/null 2>&1; then
  if curl -fsS --max-time 2 "$RECOMMEND_METRICS_URL" >/dev/null; then
    "$PYTHON_BIN" "$ROOT_DIR/scripts/eval/chat_recommend_eval.py" \
      --metrics-url "$RECOMMEND_METRICS_URL" \
      --session-id "$RECOMMEND_SESSION_ID" \
      --require-min-samples \
      --min-samples "$RECOMMEND_MIN_SAMPLES" \
      --max-block-rate "$RECOMMEND_MAX_BLOCK_RATE" \
      --max-auto-disable-total "$RECOMMEND_MAX_AUTO_DISABLE_TOTAL" \
      --out "$RECOMMEND_REPORT_OUT"
  else
    echo "  - metrics endpoint unavailable ($RECOMMEND_METRICS_URL); skipping recommend eval report"
  fi
else
  echo "  - curl not found; skipping recommend eval report"
fi

echo "[DONE] chat recommendation quality loop completed"
