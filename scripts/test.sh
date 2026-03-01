#!/usr/bin/env bash
set -euo pipefail

echo "[1/10] Contract validation (optional)"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN=""
if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

if [ -n "$PYTHON_BIN" ]; then
  if $PYTHON_BIN -c "import jsonschema" >/dev/null 2>&1; then
    $PYTHON_BIN "$ROOT_DIR/scripts/validate_contracts.py"
  else
    echo "  - jsonschema not found; skipping (install: $PYTHON_BIN -m pip install jsonschema)"
  fi
else
  echo "  - python not found; skipping contract validation"
fi

echo "[2/10] Contract compatibility gate (optional)"

echo "[3/10] Event schema compatibility check (optional)"
if [ "${RUN_SCHEMA_CHECK:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    $PYTHON_BIN "$ROOT_DIR/scripts/kafka/schema_compat_check.py" || exit 1
  else
    echo "  - python not found; skipping event schema check"
  fi
else
  echo "  - set RUN_SCHEMA_CHECK=1 to enable"
fi
if [ -n "$PYTHON_BIN" ]; then
  $PYTHON_BIN "$ROOT_DIR/scripts/contract_compat_check.py" || exit 1
else
  echo "  - python not found; skipping contract compatibility check"
fi

echo "[4/10] Feature spec validation (optional)"
if [ -n "$PYTHON_BIN" ]; then
  if $PYTHON_BIN -c "import yaml" >/dev/null 2>&1; then
    $PYTHON_BIN "$ROOT_DIR/scripts/validate_feature_spec.py" || exit 1
  else
    echo "  - PyYAML not found; skipping (install: $PYTHON_BIN -m pip install pyyaml)"
  fi
else
  echo "  - python not found; skipping feature spec validation"
fi

echo "[5/10] Offline eval gate (optional)"
if [ "${RUN_EVAL:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    EVAL_RUN_PATH="${EVAL_RUN_PATH:-$ROOT_DIR/evaluation/runs/sample_run.jsonl}"
    EVAL_BASELINE_PATH="${EVAL_BASELINE_PATH:-$ROOT_DIR/evaluation/baseline.json}"
    $PYTHON_BIN "$ROOT_DIR/scripts/eval/run_eval.py" --run "$EVAL_RUN_PATH" --baseline "$EVAL_BASELINE_PATH" --gate || exit 1
  else
    echo "  - python not found; skipping eval gate"
  fi
else
  echo "  - set RUN_EVAL=1 to enable"
fi

echo "[6/10] Rerank eval gate (optional)"
if [ "${RUN_RERANK_EVAL:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    RERANK_BASELINE_PATH="${RERANK_BASELINE_PATH:-$ROOT_DIR/data/eval/reports/rerank_eval_sample.json}"
    RERANK_MIS_URL="${RERANK_MIS_URL:-http://localhost:8005}"
    RERANK_RANKING_URL="${RERANK_RANKING_URL:-http://localhost:8082}"
    RERANK_OS_URL="${RERANK_OS_URL:-http://localhost:9200}"
    RERANK_MIS_MODEL="${RERANK_MIS_MODEL:-multilingual-e5-small}"
    RERANK_ALLOW_MODEL_FALLBACK_GATE="${RERANK_ALLOW_MODEL_FALLBACK_GATE:-0}"
    RERANK_DEPS_OK=1
    RERANK_MODEL_FALLBACK_USED=0

    if command -v curl >/dev/null 2>&1; then
      if ! curl -fsS --max-time 2 "$RERANK_RANKING_URL/health" >/dev/null; then
        echo "  - rerank eval skipped: ranking service unavailable ($RERANK_RANKING_URL)"
        RERANK_DEPS_OK=0
      fi
      if ! curl -fsS --max-time 2 "$RERANK_OS_URL" >/dev/null; then
        echo "  - rerank eval skipped: OpenSearch unavailable ($RERANK_OS_URL)"
        RERANK_DEPS_OK=0
      fi
      if ! curl -fsS --max-time 2 -X POST "$RERANK_MIS_URL/v1/embed" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"$RERANK_MIS_MODEL\",\"texts\":[\"probe\"],\"normalize\":true}" >/dev/null; then
        if ! curl -fsS --max-time 2 -X POST "$RERANK_MIS_URL/v1/embed" \
          -H "Content-Type: application/json" \
          -d '{"texts":["probe"],"normalize":true}' >/dev/null; then
          echo "  - rerank eval skipped: MIS embed unavailable ($RERANK_MIS_URL, model=$RERANK_MIS_MODEL)"
          RERANK_DEPS_OK=0
        else
          echo "  - rerank eval: requested MIS model unavailable, using MIS default embed model"
          RERANK_MIS_MODEL=""
          RERANK_MODEL_FALLBACK_USED=1
        fi
      fi
    else
      echo "  - curl not found; running rerank eval without dependency precheck"
    fi

    if [ "$RERANK_MODEL_FALLBACK_USED" = "1" ] && [ "$RERANK_ALLOW_MODEL_FALLBACK_GATE" != "1" ]; then
      echo "  - rerank eval skipped: baseline comparability requires requested MIS model (set RERANK_ALLOW_MODEL_FALLBACK_GATE=1 to force)"
      RERANK_DEPS_OK=0
    fi

    if [ "$RERANK_DEPS_OK" = "1" ]; then
      RERANK_ARGS=(
        "$ROOT_DIR/scripts/eval/rerank_eval.py"
        --baseline-report "$RERANK_BASELINE_PATH"
        --gate
        --mis-url "$RERANK_MIS_URL"
        --ranking-url "$RERANK_RANKING_URL"
        --os-url "$RERANK_OS_URL"
      )
      if [ -n "$RERANK_MIS_MODEL" ]; then
        RERANK_ARGS+=(--mis-model "$RERANK_MIS_MODEL")
      fi
      $PYTHON_BIN "${RERANK_ARGS[@]}" || exit 1
    fi
  else
    echo "  - python not found; skipping rerank eval gate"
  fi
else
  echo "  - set RUN_RERANK_EVAL=1 to enable"
fi

echo "[7/10] Chat recommend/rollout eval gate (optional)"
if [ "${RUN_CHAT_RECOMMEND_EVAL:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_RECOMMEND_METRICS_URL="${CHAT_RECOMMEND_METRICS_URL:-http://localhost:8001/metrics}"
    CHAT_RECOMMEND_SESSION_ID="${CHAT_RECOMMEND_SESSION_ID:-u:101:default}"
    CHAT_RECOMMEND_TIMEOUT="${CHAT_RECOMMEND_TIMEOUT:-2.0}"
    CHAT_RECOMMEND_MIN_SAMPLES="${CHAT_RECOMMEND_MIN_SAMPLES:-20}"
    CHAT_RECOMMEND_MAX_BLOCK_RATE="${CHAT_RECOMMEND_MAX_BLOCK_RATE:-0.4}"
    CHAT_RECOMMEND_MAX_AUTO_DISABLE_TOTAL="${CHAT_RECOMMEND_MAX_AUTO_DISABLE_TOTAL:-0}"
    CHAT_RECOMMEND_REQUIRE_MIN_SAMPLES="${CHAT_RECOMMEND_REQUIRE_MIN_SAMPLES:-1}"
    CHAT_RECOMMEND_BASELINE_PATH="${CHAT_RECOMMEND_BASELINE_PATH:-$ROOT_DIR/data/eval/reports/chat_recommend_eval_baseline.json}"

    CHAT_RECOMMEND_DEPS_OK=1
    if command -v curl >/dev/null 2>&1; then
      if ! curl -fsS --max-time 2 "$CHAT_RECOMMEND_METRICS_URL" >/dev/null; then
        echo "  - chat recommend eval skipped: metrics endpoint unavailable ($CHAT_RECOMMEND_METRICS_URL)"
        CHAT_RECOMMEND_DEPS_OK=0
      fi
    else
      echo "  - curl not found; running chat recommend eval without dependency precheck"
    fi

    if [ "$CHAT_RECOMMEND_DEPS_OK" = "1" ]; then
      CHAT_RECOMMEND_ARGS=(
        "$ROOT_DIR/scripts/eval/chat_recommend_eval.py"
        --metrics-url "$CHAT_RECOMMEND_METRICS_URL"
        --session-id "$CHAT_RECOMMEND_SESSION_ID"
        --timeout "$CHAT_RECOMMEND_TIMEOUT"
        --min-samples "$CHAT_RECOMMEND_MIN_SAMPLES"
        --max-block-rate "$CHAT_RECOMMEND_MAX_BLOCK_RATE"
        --max-auto-disable-total "$CHAT_RECOMMEND_MAX_AUTO_DISABLE_TOTAL"
        --gate
      )
      if [ "$CHAT_RECOMMEND_REQUIRE_MIN_SAMPLES" = "1" ]; then
        CHAT_RECOMMEND_ARGS+=(--require-min-samples)
      fi
      if [ -f "$CHAT_RECOMMEND_BASELINE_PATH" ]; then
        CHAT_RECOMMEND_ARGS+=(--baseline-report "$CHAT_RECOMMEND_BASELINE_PATH")
      fi
      $PYTHON_BIN "${CHAT_RECOMMEND_ARGS[@]}" || exit 1
    fi
  else
    echo "  - python not found; skipping chat recommend eval gate"
  fi
else
  echo "  - set RUN_CHAT_RECOMMEND_EVAL=1 to enable"
fi

if [ "${RUN_CHAT_ROLLOUT_EVAL:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_ROLLOUT_METRICS_URL="${CHAT_ROLLOUT_METRICS_URL:-http://localhost:8001/metrics}"
    CHAT_ROLLOUT_URL="${CHAT_ROLLOUT_URL:-http://localhost:8001/internal/chat/rollout}"
    CHAT_ROLLOUT_TIMEOUT="${CHAT_ROLLOUT_TIMEOUT:-2.0}"
    CHAT_ROLLOUT_MIN_AGENT_SAMPLES="${CHAT_ROLLOUT_MIN_AGENT_SAMPLES:-20}"
    CHAT_ROLLOUT_MAX_FAILURE_RATIO="${CHAT_ROLLOUT_MAX_FAILURE_RATIO:-0.2}"
    CHAT_ROLLOUT_MAX_ROLLBACK_TOTAL="${CHAT_ROLLOUT_MAX_ROLLBACK_TOTAL:-0}"
    CHAT_ROLLOUT_REQUIRE_MIN_SAMPLES="${CHAT_ROLLOUT_REQUIRE_MIN_SAMPLES:-1}"
    CHAT_ROLLOUT_ALLOW_ACTIVE_ROLLBACK="${CHAT_ROLLOUT_ALLOW_ACTIVE_ROLLBACK:-0}"
    CHAT_ROLLOUT_BASELINE_PATH="${CHAT_ROLLOUT_BASELINE_PATH:-$ROOT_DIR/data/eval/reports/chat_rollout_eval_baseline.json}"

    CHAT_ROLLOUT_DEPS_OK=1
    if command -v curl >/dev/null 2>&1; then
      if ! curl -fsS --max-time 2 "$CHAT_ROLLOUT_METRICS_URL" >/dev/null; then
        echo "  - chat rollout eval skipped: metrics endpoint unavailable ($CHAT_ROLLOUT_METRICS_URL)"
        CHAT_ROLLOUT_DEPS_OK=0
      fi
      if ! curl -fsS --max-time 2 "$CHAT_ROLLOUT_URL" >/dev/null; then
        echo "  - chat rollout eval skipped: rollout endpoint unavailable ($CHAT_ROLLOUT_URL)"
        CHAT_ROLLOUT_DEPS_OK=0
      fi
    else
      echo "  - curl not found; running chat rollout eval without dependency precheck"
    fi

    if [ "$CHAT_ROLLOUT_DEPS_OK" = "1" ]; then
      CHAT_ROLLOUT_ARGS=(
        "$ROOT_DIR/scripts/eval/chat_rollout_eval.py"
        --metrics-url "$CHAT_ROLLOUT_METRICS_URL"
        --rollout-url "$CHAT_ROLLOUT_URL"
        --timeout "$CHAT_ROLLOUT_TIMEOUT"
        --min-agent-samples "$CHAT_ROLLOUT_MIN_AGENT_SAMPLES"
        --max-failure-ratio "$CHAT_ROLLOUT_MAX_FAILURE_RATIO"
        --max-rollback-total "$CHAT_ROLLOUT_MAX_ROLLBACK_TOTAL"
        --gate
      )
      if [ "$CHAT_ROLLOUT_REQUIRE_MIN_SAMPLES" = "1" ]; then
        CHAT_ROLLOUT_ARGS+=(--require-min-samples)
      fi
      if [ "$CHAT_ROLLOUT_ALLOW_ACTIVE_ROLLBACK" = "1" ]; then
        CHAT_ROLLOUT_ARGS+=(--allow-active-rollback)
      fi
      if [ -f "$CHAT_ROLLOUT_BASELINE_PATH" ]; then
        CHAT_ROLLOUT_ARGS+=(--baseline-report "$CHAT_ROLLOUT_BASELINE_PATH")
      fi
      $PYTHON_BIN "${CHAT_ROLLOUT_ARGS[@]}" || exit 1
    fi
  else
    echo "  - python not found; skipping chat rollout eval gate"
  fi
else
  echo "  - set RUN_CHAT_ROLLOUT_EVAL=1 to enable"
fi

echo "[8/10] Canonical quality checks (optional)"
if [ "${RUN_CANONICAL_CHECKS:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    $PYTHON_BIN "$ROOT_DIR/scripts/canonical/validate_canonical.py" || exit 1
  else
    echo "  - python not found; skipping canonical checks"
  fi
else
  echo "  - set RUN_CANONICAL_CHECKS=1 to enable"
fi

echo "[9/10] E2E tests (optional)"
if [ "${RUN_E2E:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    $PYTHON_BIN "$ROOT_DIR/scripts/e2e/e2e_commerce_flow.py" || exit 1
  else
    echo "  - python not found; skipping E2E"
  fi
else
  echo "  - set RUN_E2E=1 to enable"
fi

echo "[10/10] Done"
