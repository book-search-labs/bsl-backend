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
FEEDBACK_REGRESSION_SEEDS_JSON="${CHAT_FEEDBACK_REGRESSION_SEEDS_JSON:-$ROOT_DIR/evaluation/chat/feedback_regression_seeds.json}"
FEEDBACK_REGRESSION_SEEDS_MD="${CHAT_FEEDBACK_REGRESSION_SEEDS_MD:-$ROOT_DIR/tasks/backlog/generated/chat_feedback_regression_seeds.md}"
FEEDBACK_REGRESSION_MIN_REASON_COUNT="${CHAT_FEEDBACK_REGRESSION_MIN_REASON_COUNT:-3}"
FEEDBACK_REGRESSION_MAX_ITEMS="${CHAT_FEEDBACK_REGRESSION_MAX_ITEMS:-12}"
FEEDBACK_REGRESSION_ALLOW_EMPTY="${CHAT_FEEDBACK_REGRESSION_ALLOW_EMPTY:-1}"
FEEDBACK_DAYS="${CHAT_FEEDBACK_DAYS:-7}"
FEEDBACK_SINCE="${CHAT_FEEDBACK_SINCE:-}"
FEEDBACK_INCLUDE_COMMENT="${CHAT_FEEDBACK_INCLUDE_COMMENT:-0}"

RECOMMEND_METRICS_URL="${CHAT_RECOMMEND_METRICS_URL:-http://localhost:8001/metrics}"
RECOMMEND_SESSION_ID="${CHAT_RECOMMEND_SESSION_ID:-u:101:default}"
RECOMMEND_REPORT_OUT="${CHAT_RECOMMEND_REPORT_OUT:-$ROOT_DIR/data/eval/reports}"
RECOMMEND_MIN_SAMPLES="${CHAT_RECOMMEND_MIN_SAMPLES:-20}"
RECOMMEND_MAX_BLOCK_RATE="${CHAT_RECOMMEND_MAX_BLOCK_RATE:-0.4}"
RECOMMEND_MAX_AUTO_DISABLE_TOTAL="${CHAT_RECOMMEND_MAX_AUTO_DISABLE_TOTAL:-0}"
ROLLOUT_URL="${CHAT_ROLLOUT_URL:-http://localhost:8001/internal/chat/rollout}"
ROLLOUT_MIN_AGENT_SAMPLES="${CHAT_ROLLOUT_MIN_AGENT_SAMPLES:-20}"
ROLLOUT_MAX_FAILURE_RATIO="${CHAT_ROLLOUT_MAX_FAILURE_RATIO:-0.2}"
ROLLOUT_MAX_ROLLBACK_TOTAL="${CHAT_ROLLOUT_MAX_ROLLBACK_TOTAL:-0}"
SEMANTIC_SESSION_ID="${CHAT_SEMANTIC_SESSION_ID:-$RECOMMEND_SESSION_ID}"
SEMANTIC_MIN_QUALITY_SAMPLES="${CHAT_SEMANTIC_MIN_QUALITY_SAMPLES:-20}"
SEMANTIC_MAX_ERROR_RATE="${CHAT_SEMANTIC_MAX_ERROR_RATE:-0.2}"
SEMANTIC_MAX_AUTO_DISABLE_TOTAL="${CHAT_SEMANTIC_MAX_AUTO_DISABLE_TOTAL:-0}"
SEMANTIC_REQUIRE_MIN_SAMPLES="${CHAT_SEMANTIC_REQUIRE_MIN_SAMPLES:-1}"
REGRESSION_FIXTURE="${CHAT_REGRESSION_FIXTURE:-$ROOT_DIR/services/query-service/tests/fixtures/chat_state_regression_v1.json}"
REGRESSION_INGEST_DIR="${CHAT_REGRESSION_INGEST_DIR:-$FEEDBACK_BACKLOG_TICKETS_DIR}"
REGRESSION_MIN_SCENARIOS="${CHAT_REGRESSION_MIN_SCENARIOS:-30}"
REGRESSION_MIN_TURNS="${CHAT_REGRESSION_MIN_TURNS:-45}"
REGRESSION_MIN_MULTI_TURN="${CHAT_REGRESSION_MIN_MULTI_TURN:-12}"
REGRESSION_MIN_BOOK_SCENARIOS="${CHAT_REGRESSION_MIN_BOOK_SCENARIOS:-8}"
REGRESSION_REQUIRE_INGEST="${CHAT_REGRESSION_REQUIRE_INGEST:-0}"
REGRESSION_MIN_INGEST_CASES="${CHAT_REGRESSION_MIN_INGEST_CASES:-1}"
REGRESSION_GATE="${CHAT_REGRESSION_GATE:-0}"
AGENT_SUMMARY_ENABLED="${CHAT_AGENT_SUMMARY_ENABLED:-1}"
AGENT_SUMMARY_REQUIRE_ALL="${CHAT_AGENT_SUMMARY_REQUIRE_ALL:-0}"
AGENT_SUMMARY_GATE="${CHAT_AGENT_SUMMARY_GATE:-0}"
RECOMMEND_CAPTURE_SNAPSHOT="${CHAT_RECOMMEND_CAPTURE_SNAPSHOT:-1}"
RECOMMEND_OPS_BASE_URL="${CHAT_RECOMMEND_OPS_BASE_URL:-http://localhost:8088}"
RECOMMEND_OPS_ADMIN_ID="${CHAT_RECOMMEND_OPS_ADMIN_ID:-1}"
RECOMMEND_SNAPSHOT_BEFORE="${CHAT_RECOMMEND_SNAPSHOT_BEFORE:-$ROOT_DIR/evaluation/chat/recommend_experiment_snapshot_before.json}"
RECOMMEND_SNAPSHOT_AFTER="${CHAT_RECOMMEND_SNAPSHOT_AFTER:-$ROOT_DIR/evaluation/chat/recommend_experiment_snapshot_after.json}"
ROLLOUT_CAPTURE_SNAPSHOT="${CHAT_ROLLOUT_CAPTURE_SNAPSHOT:-1}"
ROLLOUT_SNAPSHOT_BEFORE="${CHAT_ROLLOUT_SNAPSHOT_BEFORE:-$ROOT_DIR/evaluation/chat/rollout_snapshot_before.json}"
ROLLOUT_SNAPSHOT_AFTER="${CHAT_ROLLOUT_SNAPSHOT_AFTER:-$ROOT_DIR/evaluation/chat/rollout_snapshot_after.json}"

if [ "$RECOMMEND_CAPTURE_SNAPSHOT" = "1" ]; then
  echo "[0/3] capture recommend experiment snapshot (before)"
  if "$PYTHON_BIN" "$ROOT_DIR/scripts/chat/recommend_experiment_ops.py" \
      --base-url "$RECOMMEND_OPS_BASE_URL" \
      --admin-id "$RECOMMEND_OPS_ADMIN_ID" \
      --output "$RECOMMEND_SNAPSHOT_BEFORE" \
      snapshot >/dev/null 2>&1; then
    echo "  - wrote snapshot(before): $RECOMMEND_SNAPSHOT_BEFORE"
  else
    echo "  - snapshot(before) unavailable; continuing"
  fi
fi
if [ "$ROLLOUT_CAPTURE_SNAPSHOT" = "1" ]; then
  echo "[0/3] capture chat rollout snapshot (before)"
  if "$PYTHON_BIN" "$ROOT_DIR/scripts/chat/rollout_ops.py" \
      --base-url "$RECOMMEND_OPS_BASE_URL" \
      --admin-id "$RECOMMEND_OPS_ADMIN_ID" \
      --output "$ROLLOUT_SNAPSHOT_BEFORE" \
      snapshot >/dev/null 2>&1; then
    echo "  - wrote rollout snapshot(before): $ROLLOUT_SNAPSHOT_BEFORE"
  else
    echo "  - rollout snapshot(before) unavailable; continuing"
  fi
fi

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
FEEDBACK_REGRESSION_ARGS=(
  "$ROOT_DIR/scripts/chat/generate_feedback_regression_seeds.py"
  --input "$FEEDBACK_JSONL"
  --output-json "$FEEDBACK_REGRESSION_SEEDS_JSON"
  --output-md "$FEEDBACK_REGRESSION_SEEDS_MD"
  --min-reason-count "$FEEDBACK_REGRESSION_MIN_REASON_COUNT"
  --max-items "$FEEDBACK_REGRESSION_MAX_ITEMS"
)
if [ "$FEEDBACK_REGRESSION_ALLOW_EMPTY" = "1" ]; then
  FEEDBACK_REGRESSION_ARGS+=(--allow-empty)
fi
"$PYTHON_BIN" "${FEEDBACK_REGRESSION_ARGS[@]}"

echo "[3/3] generate recommendation/rollout/semantic/regression quality reports"
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
    if curl -fsS --max-time 2 "$ROLLOUT_URL" >/dev/null; then
      "$PYTHON_BIN" "$ROOT_DIR/scripts/eval/chat_rollout_eval.py" \
        --metrics-url "$RECOMMEND_METRICS_URL" \
        --rollout-url "$ROLLOUT_URL" \
        --require-min-samples \
        --min-agent-samples "$ROLLOUT_MIN_AGENT_SAMPLES" \
        --max-failure-ratio "$ROLLOUT_MAX_FAILURE_RATIO" \
        --max-rollback-total "$ROLLOUT_MAX_ROLLBACK_TOTAL" \
        --out "$RECOMMEND_REPORT_OUT"
    else
      echo "  - rollout endpoint unavailable ($ROLLOUT_URL); skipping rollout eval report"
    fi
    SEMANTIC_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_semantic_cache_eval.py"
      --metrics-url "$RECOMMEND_METRICS_URL"
      --session-id "$SEMANTIC_SESSION_ID"
      --min-quality-samples "$SEMANTIC_MIN_QUALITY_SAMPLES"
      --max-error-rate "$SEMANTIC_MAX_ERROR_RATE"
      --max-auto-disable-total "$SEMANTIC_MAX_AUTO_DISABLE_TOTAL"
      --out "$RECOMMEND_REPORT_OUT"
    )
    if [ "$SEMANTIC_REQUIRE_MIN_SAMPLES" = "1" ]; then
      SEMANTIC_ARGS+=(--require-min-samples)
    fi
    "$PYTHON_BIN" "${SEMANTIC_ARGS[@]}"
  else
    echo "  - metrics endpoint unavailable ($RECOMMEND_METRICS_URL); skipping recommend/rollout/semantic eval reports"
  fi
else
  echo "  - curl not found; skipping recommend/rollout/semantic eval reports"
fi

if [ -f "$REGRESSION_FIXTURE" ]; then
  REGRESSION_ARGS=(
    "$ROOT_DIR/scripts/eval/chat_regression_suite_eval.py"
    --fixture "$REGRESSION_FIXTURE"
    --ingest-dir "$REGRESSION_INGEST_DIR"
    --min-scenarios "$REGRESSION_MIN_SCENARIOS"
    --min-turns "$REGRESSION_MIN_TURNS"
    --min-multi-turn-scenarios "$REGRESSION_MIN_MULTI_TURN"
    --min-book-scenarios "$REGRESSION_MIN_BOOK_SCENARIOS"
    --min-ingest-cases "$REGRESSION_MIN_INGEST_CASES"
    --out "$RECOMMEND_REPORT_OUT"
  )
  if [ "$REGRESSION_REQUIRE_INGEST" = "1" ]; then
    REGRESSION_ARGS+=(--require-ingest)
  fi
  if [ "$REGRESSION_GATE" = "1" ]; then
    REGRESSION_ARGS+=(--gate)
  fi
  "$PYTHON_BIN" "${REGRESSION_ARGS[@]}"
else
  echo "  - regression fixture unavailable ($REGRESSION_FIXTURE); skipping regression eval report"
fi

if [ "$AGENT_SUMMARY_ENABLED" = "1" ]; then
  AGENT_SUMMARY_ARGS=(
    "$ROOT_DIR/scripts/eval/chat_agent_eval_summary.py"
    --reports-dir "$RECOMMEND_REPORT_OUT"
    --out "$RECOMMEND_REPORT_OUT"
  )
  if [ "$AGENT_SUMMARY_REQUIRE_ALL" = "1" ]; then
    AGENT_SUMMARY_ARGS+=(--require-all)
  fi
  if [ "$AGENT_SUMMARY_GATE" = "1" ]; then
    AGENT_SUMMARY_ARGS+=(--gate)
  fi
  "$PYTHON_BIN" "${AGENT_SUMMARY_ARGS[@]}"
fi

if [ "$RECOMMEND_CAPTURE_SNAPSHOT" = "1" ]; then
  echo "[post] capture recommend experiment snapshot (after)"
  if "$PYTHON_BIN" "$ROOT_DIR/scripts/chat/recommend_experiment_ops.py" \
      --base-url "$RECOMMEND_OPS_BASE_URL" \
      --admin-id "$RECOMMEND_OPS_ADMIN_ID" \
      --output "$RECOMMEND_SNAPSHOT_AFTER" \
      snapshot >/dev/null 2>&1; then
    echo "  - wrote snapshot(after): $RECOMMEND_SNAPSHOT_AFTER"
  else
    echo "  - snapshot(after) unavailable; continuing"
  fi
fi
if [ "$ROLLOUT_CAPTURE_SNAPSHOT" = "1" ]; then
  echo "[post] capture chat rollout snapshot (after)"
  if "$PYTHON_BIN" "$ROOT_DIR/scripts/chat/rollout_ops.py" \
      --base-url "$RECOMMEND_OPS_BASE_URL" \
      --admin-id "$RECOMMEND_OPS_ADMIN_ID" \
      --output "$ROLLOUT_SNAPSHOT_AFTER" \
      snapshot >/dev/null 2>&1; then
    echo "  - wrote rollout snapshot(after): $ROLLOUT_SNAPSHOT_AFTER"
  else
    echo "  - rollout snapshot(after) unavailable; continuing"
  fi
fi

echo "[DONE] chat recommendation quality loop completed"
