#!/usr/bin/env bash
set -euo pipefail

echo "[1/17] Contract validation (optional)"
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

echo "[2/17] Contract compatibility gate (optional)"

echo "[3/17] Event schema compatibility check (optional)"
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

echo "[4/17] Feature spec validation (optional)"
if [ -n "$PYTHON_BIN" ]; then
  if $PYTHON_BIN -c "import yaml" >/dev/null 2>&1; then
    $PYTHON_BIN "$ROOT_DIR/scripts/validate_feature_spec.py" || exit 1
  else
    echo "  - PyYAML not found; skipping (install: $PYTHON_BIN -m pip install pyyaml)"
  fi
else
  echo "  - python not found; skipping feature spec validation"
fi

echo "[5/17] Offline eval gate (optional)"
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

echo "[6/17] Rerank eval gate (optional)"
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

echo "[7/17] Chat contract compatibility gate (optional)"
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

echo "[8/17] Chat reason taxonomy gate (optional)"
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

echo "[9/17] Chat full eval matrix (optional)"
if [ "${RUN_CHAT_ALL_EVALS:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_PARITY_OUT_DIR="${CHAT_PARITY_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_PARITY_REPLAY_DIR="${CHAT_PARITY_REPLAY_DIR:-$ROOT_DIR/var/chat_graph/replay}"
    CHAT_PARITY_SHADOW_LIMIT="${CHAT_PARITY_SHADOW_LIMIT:-200}"
    CHAT_PARITY_RUN_SAMPLE_LIMIT="${CHAT_PARITY_RUN_SAMPLE_LIMIT:-50}"
    CHAT_PARITY_MAX_MISMATCH_RATIO="${CHAT_PARITY_MAX_MISMATCH_RATIO:-0.10}"
    CHAT_PARITY_MAX_BLOCKER_RATIO="${CHAT_PARITY_MAX_BLOCKER_RATIO:-0.02}"

    $PYTHON_BIN "$ROOT_DIR/scripts/eval/chat_graph_parity_eval.py" \
      --shadow-limit "$CHAT_PARITY_SHADOW_LIMIT" \
      --replay-dir "$CHAT_PARITY_REPLAY_DIR" \
      --run-sample-limit "$CHAT_PARITY_RUN_SAMPLE_LIMIT" \
      --max-mismatch-ratio "$CHAT_PARITY_MAX_MISMATCH_RATIO" \
      --max-blocker-ratio "$CHAT_PARITY_MAX_BLOCKER_RATIO" \
      --out "$CHAT_PARITY_OUT_DIR" \
      --gate || exit 1

    CHAT_MATRIX_BASELINE_PATH="${CHAT_MATRIX_BASELINE_PATH:-$ROOT_DIR/data/eval/reports/chat_eval_matrix_baseline.json}"
    CHAT_MATRIX_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_eval_matrix.py"
      --cases-json "${CHAT_CONTRACT_CASES_PATH:-$ROOT_DIR/services/query-service/tests/fixtures/chat_contract_compat_v1.json}"
      --responses-json "${CHAT_REASON_RESPONSES_PATH:-$ROOT_DIR/services/query-service/tests/fixtures/chat_reason_taxonomy_responses_v1.json}"
      --contracts-root "$ROOT_DIR"
      --replay-dir "$CHAT_PARITY_REPLAY_DIR"
      --shadow-limit "$CHAT_PARITY_SHADOW_LIMIT"
      --parity-run-sample-limit "$CHAT_PARITY_RUN_SAMPLE_LIMIT"
      --out "$CHAT_PARITY_OUT_DIR"
      --gate
    )
    if [ -f "$CHAT_MATRIX_BASELINE_PATH" ]; then
      CHAT_MATRIX_ARGS+=(--baseline-report "$CHAT_MATRIX_BASELINE_PATH")
    fi
    $PYTHON_BIN "${CHAT_MATRIX_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat full eval matrix"
  fi
else
  echo "  - set RUN_CHAT_ALL_EVALS=1 to enable"
fi

echo "[10/17] Chat cutover gate (optional)"
if [ "${RUN_CHAT_CUTOVER_GATE:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_CUTOVER_CURRENT_STAGE="${CHAT_CUTOVER_CURRENT_STAGE:-10}"
    CHAT_CUTOVER_DWELL_MINUTES="${CHAT_CUTOVER_DWELL_MINUTES:-0}"
    CHAT_CUTOVER_SHADOW_LIMIT="${CHAT_PARITY_SHADOW_LIMIT:-200}"
    CHAT_CUTOVER_PERF_LIMIT="${CHAT_CUTOVER_PERF_LIMIT:-500}"

    $PYTHON_BIN "$ROOT_DIR/scripts/eval/chat_cutover_gate.py" \
      --current-stage "$CHAT_CUTOVER_CURRENT_STAGE" \
      --dwell-minutes "$CHAT_CUTOVER_DWELL_MINUTES" \
      --shadow-limit "$CHAT_CUTOVER_SHADOW_LIMIT" \
      --perf-limit "$CHAT_CUTOVER_PERF_LIMIT" || exit 1
  else
    echo "  - python not found; skipping chat cutover gate"
  fi
else
  echo "  - set RUN_CHAT_CUTOVER_GATE=1 to enable"
fi

echo "[11/17] Chat legacy decommission gate (optional)"
if [ "${RUN_CHAT_LEGACY_DECOMMISSION_CHECK:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_LEGACY_DECOMMISSION_LIMIT="${CHAT_LEGACY_DECOMMISSION_LIMIT:-500}"
    CHAT_LEGACY_DECOMMISSION_MIN_WINDOW="${CHAT_LEGACY_DECOMMISSION_MIN_WINDOW:-20}"
    CHAT_LEGACY_DECOMMISSION_MAX_COUNT="${CHAT_LEGACY_DECOMMISSION_MAX_COUNT:-0}"
    CHAT_LEGACY_DECOMMISSION_MAX_RATIO="${CHAT_LEGACY_DECOMMISSION_MAX_RATIO:-0.0}"
    CHAT_LEGACY_DECOMMISSION_ALLOW_REASONS="${CHAT_LEGACY_DECOMMISSION_ALLOW_REASONS:-legacy_emergency_recovery,auto_rollback_override}"

    $PYTHON_BIN "$ROOT_DIR/scripts/eval/chat_legacy_decommission_check.py" \
      --limit "$CHAT_LEGACY_DECOMMISSION_LIMIT" \
      --min-window "$CHAT_LEGACY_DECOMMISSION_MIN_WINDOW" \
      --max-legacy-count "$CHAT_LEGACY_DECOMMISSION_MAX_COUNT" \
      --max-legacy-ratio "$CHAT_LEGACY_DECOMMISSION_MAX_RATIO" \
      --allow-legacy-reasons "$CHAT_LEGACY_DECOMMISSION_ALLOW_REASONS" \
      --gate || exit 1
  else
    echo "  - python not found; skipping chat legacy decommission gate"
  fi
else
  echo "  - set RUN_CHAT_LEGACY_DECOMMISSION_CHECK=1 to enable"
fi

echo "[12/17] Chat production launch gate (optional)"
if [ "${RUN_CHAT_PROD_LAUNCH_GATE:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_PROD_LAUNCH_OUT_DIR="${CHAT_PROD_LAUNCH_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_PROD_LAUNCH_REPLAY_DIR="${CHAT_PROD_LAUNCH_REPLAY_DIR:-$ROOT_DIR/var/chat_graph/replay}"
    CHAT_PROD_LAUNCH_COMPLETION_SOURCE="${CHAT_PROD_LAUNCH_COMPLETION_SOURCE:-auto}"
    CHAT_PROD_LAUNCH_PARITY_LIMIT="${CHAT_PROD_LAUNCH_PARITY_LIMIT:-200}"
    CHAT_PROD_LAUNCH_PERF_LIMIT="${CHAT_PROD_LAUNCH_PERF_LIMIT:-500}"
    CHAT_PROD_LAUNCH_REASON_LIMIT="${CHAT_PROD_LAUNCH_REASON_LIMIT:-500}"
    CHAT_PROD_LAUNCH_LEGACY_LIMIT="${CHAT_PROD_LAUNCH_LEGACY_LIMIT:-500}"
    CHAT_PROD_LAUNCH_RUN_LIMIT="${CHAT_PROD_LAUNCH_RUN_LIMIT:-300}"
    CHAT_PROD_LAUNCH_MIN_REASON_WINDOW="${CHAT_PROD_LAUNCH_MIN_REASON_WINDOW:-20}"
    CHAT_PROD_LAUNCH_MIN_LEGACY_WINDOW="${CHAT_PROD_LAUNCH_MIN_LEGACY_WINDOW:-20}"
    CHAT_PROD_LAUNCH_MIN_RUN_WINDOW="${CHAT_PROD_LAUNCH_MIN_RUN_WINDOW:-20}"
    CHAT_PROD_LAUNCH_MIN_COMMERCE_SAMPLES="${CHAT_PROD_LAUNCH_MIN_COMMERCE_SAMPLES:-10}"
    CHAT_PROD_LAUNCH_MAX_MISMATCH_RATIO="${CHAT_PROD_LAUNCH_MAX_MISMATCH_RATIO:-0.10}"
    CHAT_PROD_LAUNCH_MAX_BLOCKER_RATIO="${CHAT_PROD_LAUNCH_MAX_BLOCKER_RATIO:-0.02}"
    CHAT_PROD_LAUNCH_MAX_REASON_INVALID_RATIO="${CHAT_PROD_LAUNCH_MAX_REASON_INVALID_RATIO:-0.0}"
    CHAT_PROD_LAUNCH_MAX_REASON_UNKNOWN_RATIO="${CHAT_PROD_LAUNCH_MAX_REASON_UNKNOWN_RATIO:-0.05}"
    CHAT_PROD_LAUNCH_MAX_LEGACY_RATIO="${CHAT_PROD_LAUNCH_MAX_LEGACY_RATIO:-0.0}"
    CHAT_PROD_LAUNCH_MAX_LEGACY_COUNT="${CHAT_PROD_LAUNCH_MAX_LEGACY_COUNT:-0}"
    CHAT_PROD_LAUNCH_MIN_COMPLETION_RATE="${CHAT_PROD_LAUNCH_MIN_COMPLETION_RATE:-0.90}"
    CHAT_PROD_LAUNCH_MAX_INSUFFICIENT_RATIO="${CHAT_PROD_LAUNCH_MAX_INSUFFICIENT_RATIO:-0.30}"
    CHAT_PROD_LAUNCH_MODEL_VERSION="${CHAT_PROD_LAUNCH_MODEL_VERSION:-${QS_LLM_MODEL:-}}"
    CHAT_PROD_LAUNCH_PROMPT_VERSION="${CHAT_PROD_LAUNCH_PROMPT_VERSION:-${QS_CHAT_PROMPT_VERSION:-}}"
    CHAT_PROD_LAUNCH_POLICY_VERSION="${CHAT_PROD_LAUNCH_POLICY_VERSION:-${QS_CHAT_POLICY_VERSION:-}}"
    CHAT_PROD_LAUNCH_BASELINE_PATH="${CHAT_PROD_LAUNCH_BASELINE_PATH:-$ROOT_DIR/data/eval/reports/chat_production_launch_gate_baseline.json}"
    CHAT_PROD_LAUNCH_TRIAGE_OUT="${CHAT_PROD_LAUNCH_TRIAGE_OUT:-$ROOT_DIR/var/chat_graph/triage/chat_launch_failure_cases.jsonl}"
    CHAT_PROD_LAUNCH_TRIAGE_MAX="${CHAT_PROD_LAUNCH_TRIAGE_MAX:-50}"
    CHAT_PROD_LAUNCH_MAX_MISMATCH_INCREASE="${CHAT_PROD_LAUNCH_MAX_MISMATCH_INCREASE:-0.01}"
    CHAT_PROD_LAUNCH_MAX_BLOCKER_INCREASE="${CHAT_PROD_LAUNCH_MAX_BLOCKER_INCREASE:-0.005}"
    CHAT_PROD_LAUNCH_MAX_REASON_INVALID_INCREASE="${CHAT_PROD_LAUNCH_MAX_REASON_INVALID_INCREASE:-0.0}"
    CHAT_PROD_LAUNCH_MAX_REASON_UNKNOWN_INCREASE="${CHAT_PROD_LAUNCH_MAX_REASON_UNKNOWN_INCREASE:-0.01}"
    CHAT_PROD_LAUNCH_MAX_LEGACY_INCREASE="${CHAT_PROD_LAUNCH_MAX_LEGACY_INCREASE:-0.0}"
    CHAT_PROD_LAUNCH_MAX_INSUFFICIENT_INCREASE="${CHAT_PROD_LAUNCH_MAX_INSUFFICIENT_INCREASE:-0.05}"
    CHAT_PROD_LAUNCH_MAX_COMPLETION_DROP="${CHAT_PROD_LAUNCH_MAX_COMPLETION_DROP:-0.03}"

    CHAT_PROD_LAUNCH_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_production_launch_gate.py"
      --out "$CHAT_PROD_LAUNCH_OUT_DIR"
      --replay-dir "$CHAT_PROD_LAUNCH_REPLAY_DIR"
      --completion-source "$CHAT_PROD_LAUNCH_COMPLETION_SOURCE"
      --parity-limit "$CHAT_PROD_LAUNCH_PARITY_LIMIT"
      --perf-limit "$CHAT_PROD_LAUNCH_PERF_LIMIT"
      --reason-limit "$CHAT_PROD_LAUNCH_REASON_LIMIT"
      --legacy-limit "$CHAT_PROD_LAUNCH_LEGACY_LIMIT"
      --run-limit "$CHAT_PROD_LAUNCH_RUN_LIMIT"
      --min-reason-window "$CHAT_PROD_LAUNCH_MIN_REASON_WINDOW"
      --min-legacy-window "$CHAT_PROD_LAUNCH_MIN_LEGACY_WINDOW"
      --min-run-window "$CHAT_PROD_LAUNCH_MIN_RUN_WINDOW"
      --min-commerce-samples "$CHAT_PROD_LAUNCH_MIN_COMMERCE_SAMPLES"
      --max-mismatch-ratio "$CHAT_PROD_LAUNCH_MAX_MISMATCH_RATIO"
      --max-blocker-ratio "$CHAT_PROD_LAUNCH_MAX_BLOCKER_RATIO"
      --max-reason-invalid-ratio "$CHAT_PROD_LAUNCH_MAX_REASON_INVALID_RATIO"
      --max-reason-unknown-ratio "$CHAT_PROD_LAUNCH_MAX_REASON_UNKNOWN_RATIO"
      --max-legacy-ratio "$CHAT_PROD_LAUNCH_MAX_LEGACY_RATIO"
      --max-legacy-count "$CHAT_PROD_LAUNCH_MAX_LEGACY_COUNT"
      --min-commerce-completion-rate "$CHAT_PROD_LAUNCH_MIN_COMPLETION_RATE"
      --max-insufficient-evidence-ratio "$CHAT_PROD_LAUNCH_MAX_INSUFFICIENT_RATIO"
      --model-version "$CHAT_PROD_LAUNCH_MODEL_VERSION"
      --prompt-version "$CHAT_PROD_LAUNCH_PROMPT_VERSION"
      --policy-version "$CHAT_PROD_LAUNCH_POLICY_VERSION"
      --max-mismatch-ratio-increase "$CHAT_PROD_LAUNCH_MAX_MISMATCH_INCREASE"
      --max-blocker-ratio-increase "$CHAT_PROD_LAUNCH_MAX_BLOCKER_INCREASE"
      --max-reason-invalid-ratio-increase "$CHAT_PROD_LAUNCH_MAX_REASON_INVALID_INCREASE"
      --max-reason-unknown-ratio-increase "$CHAT_PROD_LAUNCH_MAX_REASON_UNKNOWN_INCREASE"
      --max-legacy-ratio-increase "$CHAT_PROD_LAUNCH_MAX_LEGACY_INCREASE"
      --max-insufficient-evidence-ratio-increase "$CHAT_PROD_LAUNCH_MAX_INSUFFICIENT_INCREASE"
      --max-completion-rate-drop "$CHAT_PROD_LAUNCH_MAX_COMPLETION_DROP"
      --triage-out "$CHAT_PROD_LAUNCH_TRIAGE_OUT"
      --triage-max-samples "$CHAT_PROD_LAUNCH_TRIAGE_MAX"
      --gate
    )
    if [ -f "$CHAT_PROD_LAUNCH_BASELINE_PATH" ]; then
      CHAT_PROD_LAUNCH_ARGS+=(--baseline-report "$CHAT_PROD_LAUNCH_BASELINE_PATH")
    fi
    $PYTHON_BIN "${CHAT_PROD_LAUNCH_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat production launch gate"
  fi
else
  echo "  - set RUN_CHAT_PROD_LAUNCH_GATE=1 to enable"
fi

echo "[13/17] Chat release train gate (optional)"
if [ "${RUN_CHAT_RELEASE_TRAIN_GATE:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_RELEASE_TRAIN_REPORT_PATH="${CHAT_RELEASE_TRAIN_REPORT_PATH:-}"
    CHAT_RELEASE_TRAIN_REPORTS_DIR="${CHAT_RELEASE_TRAIN_REPORTS_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_RELEASE_TRAIN_PREFIX="${CHAT_RELEASE_TRAIN_PREFIX:-chat_production_launch_gate}"
    CHAT_RELEASE_TRAIN_STAGE="${CHAT_RELEASE_TRAIN_STAGE:-10}"
    CHAT_RELEASE_TRAIN_DWELL_MINUTES="${CHAT_RELEASE_TRAIN_DWELL_MINUTES:-0}"
    CHAT_RELEASE_TRAIN_APPLY_ROLLBACK="${CHAT_RELEASE_TRAIN_APPLY_ROLLBACK:-0}"

    CHAT_RELEASE_TRAIN_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_release_train_gate.py"
      --reports-dir "$CHAT_RELEASE_TRAIN_REPORTS_DIR"
      --report-prefix "$CHAT_RELEASE_TRAIN_PREFIX"
      --current-stage "$CHAT_RELEASE_TRAIN_STAGE"
      --dwell-minutes "$CHAT_RELEASE_TRAIN_DWELL_MINUTES"
    )
    if [ -n "$CHAT_RELEASE_TRAIN_REPORT_PATH" ]; then
      CHAT_RELEASE_TRAIN_ARGS+=(--launch-gate-report "$CHAT_RELEASE_TRAIN_REPORT_PATH")
    fi
    if [ "$CHAT_RELEASE_TRAIN_APPLY_ROLLBACK" = "1" ]; then
      CHAT_RELEASE_TRAIN_ARGS+=(--apply-rollback)
    fi
    $PYTHON_BIN "${CHAT_RELEASE_TRAIN_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat release train gate"
  fi
else
  echo "  - set RUN_CHAT_RELEASE_TRAIN_GATE=1 to enable"
fi

echo "[14/17] Chat liveops cycle (optional)"
if [ "${RUN_CHAT_LIVEOPS_CYCLE:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_LIVEOPS_OUT_DIR="${CHAT_LIVEOPS_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_LIVEOPS_REPLAY_DIR="${CHAT_LIVEOPS_REPLAY_DIR:-$ROOT_DIR/var/chat_graph/replay}"
    CHAT_LIVEOPS_COMPLETION_SOURCE="${CHAT_LIVEOPS_COMPLETION_SOURCE:-auto}"
    CHAT_LIVEOPS_CURRENT_STAGE="${CHAT_LIVEOPS_CURRENT_STAGE:-10}"
    CHAT_LIVEOPS_DWELL_MINUTES="${CHAT_LIVEOPS_DWELL_MINUTES:-0}"
    CHAT_LIVEOPS_APPLY_ROLLBACK="${CHAT_LIVEOPS_APPLY_ROLLBACK:-0}"
    CHAT_LIVEOPS_REQUIRE_PROMOTE="${CHAT_LIVEOPS_REQUIRE_PROMOTE:-0}"
    CHAT_LIVEOPS_BASELINE_PATH="${CHAT_LIVEOPS_BASELINE_PATH:-$ROOT_DIR/data/eval/reports/chat_production_launch_gate_baseline.json}"

    CHAT_LIVEOPS_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_liveops_cycle.py"
      --out "$CHAT_LIVEOPS_OUT_DIR"
      --replay-dir "$CHAT_LIVEOPS_REPLAY_DIR"
      --completion-source "$CHAT_LIVEOPS_COMPLETION_SOURCE"
      --current-stage "$CHAT_LIVEOPS_CURRENT_STAGE"
      --dwell-minutes "$CHAT_LIVEOPS_DWELL_MINUTES"
    )
    if [ -f "$CHAT_LIVEOPS_BASELINE_PATH" ]; then
      CHAT_LIVEOPS_ARGS+=(--baseline-report "$CHAT_LIVEOPS_BASELINE_PATH")
    fi
    if [ "$CHAT_LIVEOPS_APPLY_ROLLBACK" = "1" ]; then
      CHAT_LIVEOPS_ARGS+=(--apply-rollback)
    fi
    if [ "$CHAT_LIVEOPS_REQUIRE_PROMOTE" = "1" ]; then
      CHAT_LIVEOPS_ARGS+=(--require-promote)
    fi
    $PYTHON_BIN "${CHAT_LIVEOPS_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat liveops cycle"
  fi
else
  echo "  - set RUN_CHAT_LIVEOPS_CYCLE=1 to enable"
fi

echo "[15/17] Canonical quality checks (optional)"
if [ "${RUN_CANONICAL_CHECKS:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    $PYTHON_BIN "$ROOT_DIR/scripts/canonical/validate_canonical.py" || exit 1
  else
    echo "  - python not found; skipping canonical checks"
  fi
else
  echo "  - set RUN_CANONICAL_CHECKS=1 to enable"
fi

echo "[16/17] E2E tests (optional)"
if [ "${RUN_E2E:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    $PYTHON_BIN "$ROOT_DIR/scripts/e2e/e2e_commerce_flow.py" || exit 1
  else
    echo "  - python not found; skipping E2E"
  fi
else
  echo "  - set RUN_E2E=1 to enable"
fi

echo "[17/17] Done"
