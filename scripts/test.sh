#!/usr/bin/env bash
set -euo pipefail

echo "[1/11] Contract validation (optional)"
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

echo "[2/11] Contract compatibility gate (optional)"

echo "[3/11] Event schema compatibility check (optional)"
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

echo "[4/11] Feature spec validation (optional)"
if [ -n "$PYTHON_BIN" ]; then
  if $PYTHON_BIN -c "import yaml" >/dev/null 2>&1; then
    $PYTHON_BIN "$ROOT_DIR/scripts/validate_feature_spec.py" || exit 1
  else
    echo "  - PyYAML not found; skipping (install: $PYTHON_BIN -m pip install pyyaml)"
  fi
else
  echo "  - python not found; skipping feature spec validation"
fi

echo "[5/11] Offline eval gate (optional)"
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

echo "[6/11] Rerank eval gate (optional)"
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

echo "[7/11] Chat contract compatibility gate (optional)"
if [ "${RUN_CHAT_CONTRACT_COMPAT_EVAL:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_CONTRACT_CASES_PATH="${CHAT_CONTRACT_CASES_PATH:-$ROOT_DIR/services/query-service/tests/fixtures/chat_contract_compat_v1.json}"
    CHAT_CONTRACT_OUT_DIR="${CHAT_CONTRACT_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_CONTRACT_MIN_CASES="${CHAT_CONTRACT_MIN_CASES:-3}"
    CHAT_CONTRACT_REQUIRE_ALL="${CHAT_CONTRACT_REQUIRE_ALL:-1}"
    CHAT_CONTRACT_BASELINE_PATH="${CHAT_CONTRACT_BASELINE_PATH:-$ROOT_DIR/data/eval/reports/chat_contract_compat_eval_baseline.json}"
    CHAT_CONTRACT_MAX_CASE_DROP="${CHAT_CONTRACT_MAX_CASE_DROP:-0}"
    CHAT_CONTRACT_MAX_FAILURE_INCREASE="${CHAT_CONTRACT_MAX_FAILURE_INCREASE:-0}"

    CHAT_CONTRACT_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_contract_compat_eval.py"
      --cases-json "$CHAT_CONTRACT_CASES_PATH"
      --contracts-root "$ROOT_DIR"
      --out "$CHAT_CONTRACT_OUT_DIR"
      --min-cases "$CHAT_CONTRACT_MIN_CASES"
      --max-case-drop "$CHAT_CONTRACT_MAX_CASE_DROP"
      --max-failure-increase "$CHAT_CONTRACT_MAX_FAILURE_INCREASE"
      --gate
    )
    if [ "$CHAT_CONTRACT_REQUIRE_ALL" = "1" ]; then
      CHAT_CONTRACT_ARGS+=(--require-all)
    fi
    if [ -f "$CHAT_CONTRACT_BASELINE_PATH" ]; then
      CHAT_CONTRACT_ARGS+=(--baseline-report "$CHAT_CONTRACT_BASELINE_PATH")
    fi
    $PYTHON_BIN "${CHAT_CONTRACT_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat contract compatibility eval gate"
  fi
else
  echo "  - set RUN_CHAT_CONTRACT_COMPAT_EVAL=1 to enable"
fi

echo "[8/11] Chat reason taxonomy gate (optional)"
if [ "${RUN_CHAT_REASON_TAXONOMY_EVAL:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_REASON_CASES_PATH="${CHAT_REASON_CASES_PATH:-$ROOT_DIR/services/query-service/tests/fixtures/chat_reason_taxonomy_cases_v1.json}"
    CHAT_REASON_RESPONSES_PATH="${CHAT_REASON_RESPONSES_PATH:-$ROOT_DIR/services/query-service/tests/fixtures/chat_reason_taxonomy_responses_v1.json}"
    CHAT_REASON_OUT_DIR="${CHAT_REASON_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_REASON_MIN_CASES="${CHAT_REASON_MIN_CASES:-5}"
    CHAT_REASON_MIN_RESPONSE_TOTAL="${CHAT_REASON_MIN_RESPONSE_TOTAL:-1}"
    CHAT_REASON_MAX_INVALID_RATIO="${CHAT_REASON_MAX_INVALID_RATIO:-0.0}"
    CHAT_REASON_MAX_UNKNOWN_RATIO="${CHAT_REASON_MAX_UNKNOWN_RATIO:-0.05}"
    CHAT_REASON_BASELINE_PATH="${CHAT_REASON_BASELINE_PATH:-$ROOT_DIR/data/eval/reports/chat_reason_taxonomy_eval_baseline.json}"
    CHAT_REASON_MAX_INVALID_RATIO_INCREASE="${CHAT_REASON_MAX_INVALID_RATIO_INCREASE:-0.0}"
    CHAT_REASON_MAX_UNKNOWN_RATIO_INCREASE="${CHAT_REASON_MAX_UNKNOWN_RATIO_INCREASE:-0.01}"

    CHAT_REASON_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_reason_taxonomy_eval.py"
      --cases-json "$CHAT_REASON_CASES_PATH"
      --responses-json "$CHAT_REASON_RESPONSES_PATH"
      --out "$CHAT_REASON_OUT_DIR"
      --min-cases "$CHAT_REASON_MIN_CASES"
      --min-response-total "$CHAT_REASON_MIN_RESPONSE_TOTAL"
      --max-invalid-ratio "$CHAT_REASON_MAX_INVALID_RATIO"
      --max-unknown-ratio "$CHAT_REASON_MAX_UNKNOWN_RATIO"
      --max-invalid-ratio-increase "$CHAT_REASON_MAX_INVALID_RATIO_INCREASE"
      --max-unknown-ratio-increase "$CHAT_REASON_MAX_UNKNOWN_RATIO_INCREASE"
      --gate
    )
    if [ -f "$CHAT_REASON_BASELINE_PATH" ]; then
      CHAT_REASON_ARGS+=(--baseline-report "$CHAT_REASON_BASELINE_PATH")
    fi
    $PYTHON_BIN "${CHAT_REASON_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat reason taxonomy eval gate"
  fi
else
  echo "  - set RUN_CHAT_REASON_TAXONOMY_EVAL=1 to enable"
fi

echo "[9/11] Canonical quality checks (optional)"
if [ "${RUN_CANONICAL_CHECKS:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    $PYTHON_BIN "$ROOT_DIR/scripts/canonical/validate_canonical.py" || exit 1
  else
    echo "  - python not found; skipping canonical checks"
  fi
else
  echo "  - set RUN_CANONICAL_CHECKS=1 to enable"
fi

echo "[10/11] E2E tests (optional)"
if [ "${RUN_E2E:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    $PYTHON_BIN "$ROOT_DIR/scripts/e2e/e2e_commerce_flow.py" || exit 1
  else
    echo "  - python not found; skipping E2E"
  fi
else
  echo "  - set RUN_E2E=1 to enable"
fi

echo "[11/11] Done"
