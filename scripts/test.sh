#!/usr/bin/env bash
set -euo pipefail

echo "[1/25] Contract validation (optional)"
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

echo "[2/25] Contract compatibility gate (optional)"

echo "[3/25] Event schema compatibility check (optional)"
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

echo "[4/25] Feature spec validation (optional)"
if [ -n "$PYTHON_BIN" ]; then
  if $PYTHON_BIN -c "import yaml" >/dev/null 2>&1; then
    $PYTHON_BIN "$ROOT_DIR/scripts/validate_feature_spec.py" || exit 1
  else
    echo "  - PyYAML not found; skipping (install: $PYTHON_BIN -m pip install pyyaml)"
  fi
else
  echo "  - python not found; skipping feature spec validation"
fi

echo "[5/25] Offline eval gate (optional)"
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

echo "[6/25] Rerank eval gate (optional)"
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

echo "[7/25] Chat contract compatibility gate (optional)"
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

echo "[8/25] Chat reason taxonomy gate (optional)"
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

echo "[9/25] Chat full eval matrix (optional)"
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

echo "[10/25] Chat cutover gate (optional)"
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

echo "[11/25] Chat legacy decommission gate (optional)"
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

echo "[12/25] Chat production launch gate (optional)"
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

echo "[13/25] Chat release train gate (optional)"
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

echo "[14/25] Chat liveops cycle (optional)"
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

echo "[15/25] Chat liveops summary gate (optional)"
if [ "${RUN_CHAT_LIVEOPS_SUMMARY_GATE:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_LIVEOPS_SUMMARY_REPORTS_DIR="${CHAT_LIVEOPS_SUMMARY_REPORTS_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_LIVEOPS_SUMMARY_LIMIT="${CHAT_LIVEOPS_SUMMARY_LIMIT:-20}"
    CHAT_LIVEOPS_SUMMARY_MIN_WINDOW="${CHAT_LIVEOPS_SUMMARY_MIN_WINDOW:-3}"
    CHAT_LIVEOPS_SUMMARY_MIN_PASS_RATIO="${CHAT_LIVEOPS_SUMMARY_MIN_PASS_RATIO:-0.8}"
    CHAT_LIVEOPS_SUMMARY_DENY_ACTIONS="${CHAT_LIVEOPS_SUMMARY_DENY_ACTIONS:-rollback}"

    $PYTHON_BIN "$ROOT_DIR/scripts/eval/chat_liveops_summary.py" \
      --reports-dir "$CHAT_LIVEOPS_SUMMARY_REPORTS_DIR" \
      --limit "$CHAT_LIVEOPS_SUMMARY_LIMIT" \
      --min-window "$CHAT_LIVEOPS_SUMMARY_MIN_WINDOW" \
      --min-pass-ratio "$CHAT_LIVEOPS_SUMMARY_MIN_PASS_RATIO" \
      --deny-actions "$CHAT_LIVEOPS_SUMMARY_DENY_ACTIONS" \
      --gate || exit 1
  else
    echo "  - python not found; skipping chat liveops summary gate"
  fi
else
  echo "  - set RUN_CHAT_LIVEOPS_SUMMARY_GATE=1 to enable"
fi

echo "[16/25] Chat liveops incident gate (optional)"
if [ "${RUN_CHAT_LIVEOPS_INCIDENT_GATE:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_LIVEOPS_INCIDENT_REPORTS_DIR="${CHAT_LIVEOPS_INCIDENT_REPORTS_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_LIVEOPS_INCIDENT_LIMIT="${CHAT_LIVEOPS_INCIDENT_LIMIT:-20}"
    CHAT_LIVEOPS_INCIDENT_MIN_WINDOW="${CHAT_LIVEOPS_INCIDENT_MIN_WINDOW:-3}"
    CHAT_LIVEOPS_INCIDENT_MAX_MTTA_SEC="${CHAT_LIVEOPS_INCIDENT_MAX_MTTA_SEC:-600}"
    CHAT_LIVEOPS_INCIDENT_MAX_MTTR_SEC="${CHAT_LIVEOPS_INCIDENT_MAX_MTTR_SEC:-7200}"
    CHAT_LIVEOPS_INCIDENT_MAX_OPEN="${CHAT_LIVEOPS_INCIDENT_MAX_OPEN:-0}"

    $PYTHON_BIN "$ROOT_DIR/scripts/eval/chat_liveops_incident_summary.py" \
      --reports-dir "$CHAT_LIVEOPS_INCIDENT_REPORTS_DIR" \
      --limit "$CHAT_LIVEOPS_INCIDENT_LIMIT" \
      --min-window "$CHAT_LIVEOPS_INCIDENT_MIN_WINDOW" \
      --max-mtta-sec "$CHAT_LIVEOPS_INCIDENT_MAX_MTTA_SEC" \
      --max-mttr-sec "$CHAT_LIVEOPS_INCIDENT_MAX_MTTR_SEC" \
      --max-open-incidents "$CHAT_LIVEOPS_INCIDENT_MAX_OPEN" \
      --gate || exit 1
  else
    echo "  - python not found; skipping chat liveops incident gate"
  fi
else
  echo "  - set RUN_CHAT_LIVEOPS_INCIDENT_GATE=1 to enable"
fi

echo "[17/25] Chat oncall action plan (optional)"
if [ "${RUN_CHAT_ONCALL_ACTION_PLAN:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_ONCALL_TRIAGE_FILE="${CHAT_ONCALL_TRIAGE_FILE:-$ROOT_DIR/var/chat_graph/triage/chat_launch_failure_cases.jsonl}"
    CHAT_ONCALL_OUT_DIR="${CHAT_ONCALL_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_ONCALL_TOP_N="${CHAT_ONCALL_TOP_N:-5}"
    CHAT_ONCALL_REQUIRE_CASES="${CHAT_ONCALL_REQUIRE_CASES:-0}"

    CHAT_ONCALL_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_oncall_action_plan.py"
      --triage-file "$CHAT_ONCALL_TRIAGE_FILE"
      --out "$CHAT_ONCALL_OUT_DIR"
      --top-n "$CHAT_ONCALL_TOP_N"
    )
    if [ "$CHAT_ONCALL_REQUIRE_CASES" = "1" ]; then
      CHAT_ONCALL_ARGS+=(--require-cases)
    fi
    $PYTHON_BIN "${CHAT_ONCALL_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat oncall action plan"
  fi
else
  echo "  - set RUN_CHAT_ONCALL_ACTION_PLAN=1 to enable"
fi

echo "[18/25] Chat capacity/cost guard (optional)"
if [ "${RUN_CHAT_CAPACITY_COST_GUARD:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_CAPACITY_LAUNCH_REPORT="${CHAT_CAPACITY_LAUNCH_REPORT:-}"
    CHAT_CAPACITY_REPORTS_DIR="${CHAT_CAPACITY_REPORTS_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_CAPACITY_REPORT_PREFIX="${CHAT_CAPACITY_REPORT_PREFIX:-chat_production_launch_gate}"
    CHAT_CAPACITY_AUDIT_LOG="${CHAT_CAPACITY_AUDIT_LOG:-$ROOT_DIR/var/llm_gateway/audit.log}"
    CHAT_CAPACITY_AUDIT_WINDOW_MIN="${CHAT_CAPACITY_AUDIT_WINDOW_MIN:-60}"
    CHAT_CAPACITY_AUDIT_LIMIT="${CHAT_CAPACITY_AUDIT_LIMIT:-5000}"
    CHAT_CAPACITY_MAX_AUDIT_ERROR_RATIO="${CHAT_CAPACITY_MAX_AUDIT_ERROR_RATIO:-0.08}"
    CHAT_CAPACITY_MAX_COST_USD_PER_HOUR="${CHAT_CAPACITY_MAX_COST_USD_PER_HOUR:-5.0}"
    CHAT_CAPACITY_MAX_TOKENS_PER_HOUR="${CHAT_CAPACITY_MAX_TOKENS_PER_HOUR:-300000}"
    CHAT_CAPACITY_MAX_LLM_P95_MS="${CHAT_CAPACITY_MAX_LLM_P95_MS:-4000}"
    CHAT_CAPACITY_MAX_FALLBACK_RATIO="${CHAT_CAPACITY_MAX_FALLBACK_RATIO:-0.15}"
    CHAT_CAPACITY_MAX_INSUFFICIENT_RATIO="${CHAT_CAPACITY_MAX_INSUFFICIENT_RATIO:-0.30}"
    CHAT_CAPACITY_MAX_MODE="${CHAT_CAPACITY_MAX_MODE:-DEGRADE_LEVEL_1}"

    CHAT_CAPACITY_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_capacity_cost_guard.py"
      --reports-dir "$CHAT_CAPACITY_REPORTS_DIR"
      --report-prefix "$CHAT_CAPACITY_REPORT_PREFIX"
      --llm-audit-log "$CHAT_CAPACITY_AUDIT_LOG"
      --audit-window-minutes "$CHAT_CAPACITY_AUDIT_WINDOW_MIN"
      --audit-limit "$CHAT_CAPACITY_AUDIT_LIMIT"
      --max-audit-error-ratio "$CHAT_CAPACITY_MAX_AUDIT_ERROR_RATIO"
      --max-cost-usd-per-hour "$CHAT_CAPACITY_MAX_COST_USD_PER_HOUR"
      --max-tokens-per-hour "$CHAT_CAPACITY_MAX_TOKENS_PER_HOUR"
      --max-llm-p95-ms "$CHAT_CAPACITY_MAX_LLM_P95_MS"
      --max-fallback-ratio "$CHAT_CAPACITY_MAX_FALLBACK_RATIO"
      --max-insufficient-evidence-ratio "$CHAT_CAPACITY_MAX_INSUFFICIENT_RATIO"
      --max-mode "$CHAT_CAPACITY_MAX_MODE"
      --gate
    )
    if [ -n "$CHAT_CAPACITY_LAUNCH_REPORT" ]; then
      CHAT_CAPACITY_ARGS+=(--launch-gate-report "$CHAT_CAPACITY_LAUNCH_REPORT")
    fi
    $PYTHON_BIN "${CHAT_CAPACITY_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat capacity/cost guard"
  fi
else
  echo "  - set RUN_CHAT_CAPACITY_COST_GUARD=1 to enable"
fi

echo "[19/25] Chat immutable bundle guard (optional)"
if [ "${RUN_CHAT_IMMUTABLE_BUNDLE_GUARD:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_IMMUTABLE_REPORTS_DIR="${CHAT_IMMUTABLE_REPORTS_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_IMMUTABLE_PREFIX="${CHAT_IMMUTABLE_PREFIX:-chat_liveops_cycle}"
    CHAT_IMMUTABLE_LIMIT="${CHAT_IMMUTABLE_LIMIT:-20}"
    CHAT_IMMUTABLE_MIN_WINDOW="${CHAT_IMMUTABLE_MIN_WINDOW:-3}"
    CHAT_IMMUTABLE_MAX_UNIQUE="${CHAT_IMMUTABLE_MAX_UNIQUE:-2}"
    CHAT_IMMUTABLE_MAX_CHANGES="${CHAT_IMMUTABLE_MAX_CHANGES:-2}"
    CHAT_IMMUTABLE_ALLOWED_ACTIONS="${CHAT_IMMUTABLE_ALLOWED_ACTIONS:-promote,rollback}"
    CHAT_IMMUTABLE_REQUIRE_SIGNATURE="${CHAT_IMMUTABLE_REQUIRE_SIGNATURE:-1}"

    CHAT_IMMUTABLE_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_immutable_bundle_guard.py"
      --reports-dir "$CHAT_IMMUTABLE_REPORTS_DIR"
      --prefix "$CHAT_IMMUTABLE_PREFIX"
      --limit "$CHAT_IMMUTABLE_LIMIT"
      --min-window "$CHAT_IMMUTABLE_MIN_WINDOW"
      --max-unique-signatures "$CHAT_IMMUTABLE_MAX_UNIQUE"
      --max-signature-changes "$CHAT_IMMUTABLE_MAX_CHANGES"
      --allowed-change-actions "$CHAT_IMMUTABLE_ALLOWED_ACTIONS"
      --gate
    )
    if [ "$CHAT_IMMUTABLE_REQUIRE_SIGNATURE" = "1" ]; then
      CHAT_IMMUTABLE_ARGS+=(--require-signature)
    fi
    $PYTHON_BIN "${CHAT_IMMUTABLE_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat immutable bundle guard"
  fi
else
  echo "  - set RUN_CHAT_IMMUTABLE_BUNDLE_GUARD=1 to enable"
fi

echo "[20/25] Chat DR drill report (optional)"
if [ "${RUN_CHAT_DR_DRILL_REPORT:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_DR_DRILL_REPORTS_DIR="${CHAT_DR_DRILL_REPORTS_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_DR_DRILL_PREFIX="${CHAT_DR_DRILL_PREFIX:-chat_liveops_cycle}"
    CHAT_DR_DRILL_LIMIT="${CHAT_DR_DRILL_LIMIT:-40}"
    CHAT_DR_DRILL_OUT_DIR="${CHAT_DR_DRILL_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_DR_DRILL_MIN_WINDOW="${CHAT_DR_DRILL_MIN_WINDOW:-1}"
    CHAT_DR_DRILL_REQUIRE_DRILL="${CHAT_DR_DRILL_REQUIRE_DRILL:-0}"
    CHAT_DR_DRILL_MIN_RECOVERY_RATIO="${CHAT_DR_DRILL_MIN_RECOVERY_RATIO:-1.0}"
    CHAT_DR_DRILL_MAX_OPEN="${CHAT_DR_DRILL_MAX_OPEN:-0}"
    CHAT_DR_DRILL_MAX_AVG_MTTR_SEC="${CHAT_DR_DRILL_MAX_AVG_MTTR_SEC:-7200}"

    CHAT_DR_DRILL_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_dr_drill_report.py"
      --reports-dir "$CHAT_DR_DRILL_REPORTS_DIR"
      --prefix "$CHAT_DR_DRILL_PREFIX"
      --limit "$CHAT_DR_DRILL_LIMIT"
      --out "$CHAT_DR_DRILL_OUT_DIR"
      --min-window "$CHAT_DR_DRILL_MIN_WINDOW"
      --min-recovery-ratio "$CHAT_DR_DRILL_MIN_RECOVERY_RATIO"
      --max-open-drill-total "$CHAT_DR_DRILL_MAX_OPEN"
      --max-avg-mttr-sec "$CHAT_DR_DRILL_MAX_AVG_MTTR_SEC"
      --gate
    )
    if [ "$CHAT_DR_DRILL_REQUIRE_DRILL" = "1" ]; then
      CHAT_DR_DRILL_ARGS+=(--require-drill)
    fi
    $PYTHON_BIN "${CHAT_DR_DRILL_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat DR drill report"
  fi
else
  echo "  - set RUN_CHAT_DR_DRILL_REPORT=1 to enable"
fi

echo "[21/25] Chat readiness score gate (optional)"
if [ "${RUN_CHAT_READINESS_SCORE:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_READINESS_REPORTS_DIR="${CHAT_READINESS_REPORTS_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_READINESS_LAUNCH_REPORT="${CHAT_READINESS_LAUNCH_REPORT:-}"
    CHAT_READINESS_LAUNCH_PREFIX="${CHAT_READINESS_LAUNCH_PREFIX:-chat_production_launch_gate}"
    CHAT_READINESS_CYCLE_PREFIX="${CHAT_READINESS_CYCLE_PREFIX:-chat_liveops_cycle}"
    CHAT_READINESS_CYCLE_LIMIT="${CHAT_READINESS_CYCLE_LIMIT:-20}"
    CHAT_READINESS_AUDIT_LOG="${CHAT_READINESS_AUDIT_LOG:-$ROOT_DIR/var/llm_gateway/audit.log}"
    CHAT_READINESS_AUDIT_WINDOW_MIN="${CHAT_READINESS_AUDIT_WINDOW_MIN:-60}"
    CHAT_READINESS_AUDIT_LIMIT="${CHAT_READINESS_AUDIT_LIMIT:-5000}"
    CHAT_READINESS_MIN_SCORE="${CHAT_READINESS_MIN_SCORE:-80}"
    CHAT_READINESS_CAPACITY_MAX_MODE="${CHAT_READINESS_CAPACITY_MAX_MODE:-DEGRADE_LEVEL_1}"
    CHAT_READINESS_OUT_DIR="${CHAT_READINESS_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_READINESS_REQUIRE_PROMOTE="${CHAT_READINESS_REQUIRE_PROMOTE:-0}"

    CHAT_READINESS_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_readiness_score.py"
      --reports-dir "$CHAT_READINESS_REPORTS_DIR"
      --launch-prefix "$CHAT_READINESS_LAUNCH_PREFIX"
      --cycle-prefix "$CHAT_READINESS_CYCLE_PREFIX"
      --cycle-limit "$CHAT_READINESS_CYCLE_LIMIT"
      --llm-audit-log "$CHAT_READINESS_AUDIT_LOG"
      --audit-window-minutes "$CHAT_READINESS_AUDIT_WINDOW_MIN"
      --audit-limit "$CHAT_READINESS_AUDIT_LIMIT"
      --min-score "$CHAT_READINESS_MIN_SCORE"
      --capacity-max-mode "$CHAT_READINESS_CAPACITY_MAX_MODE"
      --out "$CHAT_READINESS_OUT_DIR"
      --gate
    )
    if [ -n "$CHAT_READINESS_LAUNCH_REPORT" ]; then
      CHAT_READINESS_ARGS+=(--launch-gate-report "$CHAT_READINESS_LAUNCH_REPORT")
    fi
    if [ "$CHAT_READINESS_REQUIRE_PROMOTE" = "1" ]; then
      CHAT_READINESS_ARGS+=(--require-promote)
    fi
    $PYTHON_BIN "${CHAT_READINESS_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat readiness score gate"
  fi
else
  echo "  - set RUN_CHAT_READINESS_SCORE=1 to enable"
fi

echo "[22/25] Chat gameday drillpack (optional)"
if [ "${RUN_CHAT_GAMEDAY_DRILLPACK:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_GAMEDAY_TRIAGE_FILE="${CHAT_GAMEDAY_TRIAGE_FILE:-$ROOT_DIR/var/chat_graph/triage/chat_launch_failure_cases.jsonl}"
    CHAT_GAMEDAY_TOP_REASONS="${CHAT_GAMEDAY_TOP_REASONS:-5}"
    CHAT_GAMEDAY_OUT_DIR="${CHAT_GAMEDAY_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_GAMEDAY_REQUIRE_TRIAGE="${CHAT_GAMEDAY_REQUIRE_TRIAGE:-0}"

    CHAT_GAMEDAY_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_gameday_drillpack.py"
      --triage-file "$CHAT_GAMEDAY_TRIAGE_FILE"
      --top-reasons "$CHAT_GAMEDAY_TOP_REASONS"
      --out "$CHAT_GAMEDAY_OUT_DIR"
      --gate
    )
    if [ "$CHAT_GAMEDAY_REQUIRE_TRIAGE" = "1" ]; then
      CHAT_GAMEDAY_ARGS+=(--require-triage)
    fi
    $PYTHON_BIN "${CHAT_GAMEDAY_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat gameday drillpack"
  fi
else
  echo "  - set RUN_CHAT_GAMEDAY_DRILLPACK=1 to enable"
fi

echo "[23/25] Canonical quality checks (optional)"
if [ "${RUN_CANONICAL_CHECKS:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    $PYTHON_BIN "$ROOT_DIR/scripts/canonical/validate_canonical.py" || exit 1
  else
    echo "  - python not found; skipping canonical checks"
  fi
else
  echo "  - set RUN_CANONICAL_CHECKS=1 to enable"
fi

echo "[24/25] E2E tests (optional)"
if [ "${RUN_E2E:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    $PYTHON_BIN "$ROOT_DIR/scripts/e2e/e2e_commerce_flow.py" || exit 1
  else
    echo "  - python not found; skipping E2E"
  fi
else
  echo "  - set RUN_E2E=1 to enable"
fi

echo "[25/25] Done"
