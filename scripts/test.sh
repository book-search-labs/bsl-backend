#!/usr/bin/env bash
set -euo pipefail

echo "[1/39] Contract validation (optional)"
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

echo "[2/39] Contract compatibility gate (optional)"

echo "[3/39] Event schema compatibility check (optional)"
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

echo "[4/39] Feature spec validation (optional)"
if [ -n "$PYTHON_BIN" ]; then
  if $PYTHON_BIN -c "import yaml" >/dev/null 2>&1; then
    $PYTHON_BIN "$ROOT_DIR/scripts/validate_feature_spec.py" || exit 1
  else
    echo "  - PyYAML not found; skipping (install: $PYTHON_BIN -m pip install pyyaml)"
  fi
else
  echo "  - python not found; skipping feature spec validation"
fi

echo "[5/39] Offline eval gate (optional)"
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

echo "[6/39] Rerank eval gate (optional)"
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

echo "[7/39] Chat contract compatibility gate (optional)"
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

echo "[8/39] Chat reason taxonomy gate (optional)"
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

echo "[9/39] Chat full eval matrix (optional)"
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

echo "[10/39] Chat cutover gate (optional)"
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

echo "[11/39] Chat legacy decommission gate (optional)"
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

echo "[12/39] Chat production launch gate (optional)"
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

echo "[13/39] Chat release train gate (optional)"
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

echo "[14/39] Chat liveops cycle (optional)"
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

echo "[15/39] Chat liveops summary gate (optional)"
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

echo "[16/39] Chat liveops incident gate (optional)"
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

echo "[17/39] Chat oncall action plan (optional)"
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

echo "[18/39] Chat capacity/cost guard (optional)"
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

echo "[19/39] Chat immutable bundle guard (optional)"
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

echo "[20/39] Chat DR drill report (optional)"
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

echo "[21/39] Chat readiness score gate (optional)"
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

echo "[22/39] Chat readiness trend gate (optional)"
if [ "${RUN_CHAT_READINESS_TREND:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_READINESS_TREND_REPORTS_DIR="${CHAT_READINESS_TREND_REPORTS_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_READINESS_TREND_PREFIX="${CHAT_READINESS_TREND_PREFIX:-chat_readiness_score}"
    CHAT_READINESS_TREND_LIMIT="${CHAT_READINESS_TREND_LIMIT:-200}"
    CHAT_READINESS_TREND_OUT_DIR="${CHAT_READINESS_TREND_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_READINESS_TREND_MIN_REPORTS="${CHAT_READINESS_TREND_MIN_REPORTS:-1}"
    CHAT_READINESS_TREND_MIN_WEEK_AVG="${CHAT_READINESS_TREND_MIN_WEEK_AVG:-80}"
    CHAT_READINESS_TREND_MIN_MONTH_AVG="${CHAT_READINESS_TREND_MIN_MONTH_AVG:-80}"

    $PYTHON_BIN "$ROOT_DIR/scripts/eval/chat_readiness_trend.py" \
      --reports-dir "$CHAT_READINESS_TREND_REPORTS_DIR" \
      --prefix "$CHAT_READINESS_TREND_PREFIX" \
      --limit "$CHAT_READINESS_TREND_LIMIT" \
      --out "$CHAT_READINESS_TREND_OUT_DIR" \
      --min-reports "$CHAT_READINESS_TREND_MIN_REPORTS" \
      --min-week-avg "$CHAT_READINESS_TREND_MIN_WEEK_AVG" \
      --min-month-avg "$CHAT_READINESS_TREND_MIN_MONTH_AVG" \
      --gate || exit 1
  else
    echo "  - python not found; skipping chat readiness trend gate"
  fi
else
  echo "  - set RUN_CHAT_READINESS_TREND=1 to enable"
fi

echo "[23/39] Chat gameday drillpack (optional)"
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

echo "[24/39] Chat incident feedback binding (optional)"
if [ "${RUN_CHAT_INCIDENT_FEEDBACK_BINDING:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_FEEDBACK_REPORTS_DIR="${CHAT_FEEDBACK_REPORTS_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_FEEDBACK_CYCLE_PREFIX="${CHAT_FEEDBACK_CYCLE_PREFIX:-chat_liveops_cycle}"
    CHAT_FEEDBACK_CYCLE_LIMIT="${CHAT_FEEDBACK_CYCLE_LIMIT:-40}"
    CHAT_FEEDBACK_TRIAGE_FILE="${CHAT_FEEDBACK_TRIAGE_FILE:-$ROOT_DIR/var/chat_graph/triage/chat_launch_failure_cases.jsonl}"
    CHAT_FEEDBACK_TOP_N="${CHAT_FEEDBACK_TOP_N:-5}"
    CHAT_FEEDBACK_OUT_DIR="${CHAT_FEEDBACK_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_FEEDBACK_MIN_BOUND="${CHAT_FEEDBACK_MIN_BOUND:-0}"

    CHAT_FEEDBACK_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_incident_feedback_binding.py"
      --reports-dir "$CHAT_FEEDBACK_REPORTS_DIR"
      --cycle-prefix "$CHAT_FEEDBACK_CYCLE_PREFIX"
      --cycle-limit "$CHAT_FEEDBACK_CYCLE_LIMIT"
      --triage-file "$CHAT_FEEDBACK_TRIAGE_FILE"
      --top-n "$CHAT_FEEDBACK_TOP_N"
      --out "$CHAT_FEEDBACK_OUT_DIR"
      --min-bound-categories "$CHAT_FEEDBACK_MIN_BOUND"
      --gate
    )
    $PYTHON_BIN "${CHAT_FEEDBACK_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat incident feedback binding"
  fi
else
  echo "  - set RUN_CHAT_INCIDENT_FEEDBACK_BINDING=1 to enable"
fi

echo "[25/39] Chat gameday readiness packet (optional)"
if [ "${RUN_CHAT_GAMEDAY_PACKET:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_PACKET_REPORTS_DIR="${CHAT_PACKET_REPORTS_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_PACKET_MIN_READINESS="${CHAT_PACKET_MIN_READINESS:-80}"
    CHAT_PACKET_MIN_WEEK_AVG="${CHAT_PACKET_MIN_WEEK_AVG:-80}"
    CHAT_PACKET_OUT_DIR="${CHAT_PACKET_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_PACKET_REQUIRE_ALL="${CHAT_PACKET_REQUIRE_ALL:-0}"

    CHAT_PACKET_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_gameday_readiness_packet.py"
      --reports-dir "$CHAT_PACKET_REPORTS_DIR"
      --min-readiness-score "$CHAT_PACKET_MIN_READINESS"
      --min-week-avg "$CHAT_PACKET_MIN_WEEK_AVG"
      --out "$CHAT_PACKET_OUT_DIR"
      --gate
    )
    if [ "$CHAT_PACKET_REQUIRE_ALL" = "1" ]; then
      CHAT_PACKET_ARGS+=(--require-all)
    fi
    $PYTHON_BIN "${CHAT_PACKET_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat gameday readiness packet"
  fi
else
  echo "  - set RUN_CHAT_GAMEDAY_PACKET=1 to enable"
fi

echo "[26/39] Chat data retention guard (optional)"
if [ "${RUN_CHAT_DATA_RETENTION_GUARD:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_RETENTION_EVENTS_JSONL="${CHAT_RETENTION_EVENTS_JSONL:-$ROOT_DIR/var/chat_governance/retention_events.jsonl}"
    CHAT_RETENTION_WINDOW_HOURS="${CHAT_RETENTION_WINDOW_HOURS:-72}"
    CHAT_RETENTION_LIMIT="${CHAT_RETENTION_LIMIT:-20000}"
    CHAT_RETENTION_OUT_DIR="${CHAT_RETENTION_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_RETENTION_MIN_WINDOW="${CHAT_RETENTION_MIN_WINDOW:-0}"
    CHAT_RETENTION_MAX_OVERDUE_TOTAL="${CHAT_RETENTION_MAX_OVERDUE_TOTAL:-0}"
    CHAT_RETENTION_MAX_OVERDUE_RATIO="${CHAT_RETENTION_MAX_OVERDUE_RATIO:-0.0}"
    CHAT_RETENTION_MIN_PURGE_COVERAGE="${CHAT_RETENTION_MIN_PURGE_COVERAGE:-1.0}"
    CHAT_RETENTION_MAX_UNAPPROVED_EXCEPTIONS="${CHAT_RETENTION_MAX_UNAPPROVED_EXCEPTIONS:-0}"
    CHAT_RETENTION_MAX_STALE_MINUTES="${CHAT_RETENTION_MAX_STALE_MINUTES:-180}"
    CHAT_RETENTION_MIN_TRACE_COVERAGE="${CHAT_RETENTION_MIN_TRACE_COVERAGE:-1.0}"
    CHAT_RETENTION_MAX_MISSING_TRACE_TOTAL="${CHAT_RETENTION_MAX_MISSING_TRACE_TOTAL:-0}"

    $PYTHON_BIN "$ROOT_DIR/scripts/eval/chat_data_retention_guard.py" \
      --events-jsonl "$CHAT_RETENTION_EVENTS_JSONL" \
      --window-hours "$CHAT_RETENTION_WINDOW_HOURS" \
      --limit "$CHAT_RETENTION_LIMIT" \
      --out "$CHAT_RETENTION_OUT_DIR" \
      --min-window "$CHAT_RETENTION_MIN_WINDOW" \
      --max-overdue-total "$CHAT_RETENTION_MAX_OVERDUE_TOTAL" \
      --max-overdue-ratio "$CHAT_RETENTION_MAX_OVERDUE_RATIO" \
      --min-purge-coverage-ratio "$CHAT_RETENTION_MIN_PURGE_COVERAGE" \
      --max-unapproved-exception-total "$CHAT_RETENTION_MAX_UNAPPROVED_EXCEPTIONS" \
      --max-stale-minutes "$CHAT_RETENTION_MAX_STALE_MINUTES" \
      --min-trace-coverage-ratio "$CHAT_RETENTION_MIN_TRACE_COVERAGE" \
      --max-missing-trace-total "$CHAT_RETENTION_MAX_MISSING_TRACE_TOTAL" \
      --gate || exit 1
  else
    echo "  - python not found; skipping chat data retention guard"
  fi
else
  echo "  - set RUN_CHAT_DATA_RETENTION_GUARD=1 to enable"
fi

echo "[27/39] Chat egress guardrails gate (optional)"
if [ "${RUN_CHAT_EGRESS_GUARDRAILS_GATE:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_EGRESS_EVENTS_JSONL="${CHAT_EGRESS_EVENTS_JSONL:-$ROOT_DIR/var/chat_governance/egress_events.jsonl}"
    CHAT_EGRESS_ALLOW_DESTINATIONS="${CHAT_EGRESS_ALLOW_DESTINATIONS:-llm_provider,langsmith,support_api}"
    CHAT_EGRESS_WINDOW_HOURS="${CHAT_EGRESS_WINDOW_HOURS:-24}"
    CHAT_EGRESS_LIMIT="${CHAT_EGRESS_LIMIT:-20000}"
    CHAT_EGRESS_OUT_DIR="${CHAT_EGRESS_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_EGRESS_MIN_WINDOW="${CHAT_EGRESS_MIN_WINDOW:-0}"
    CHAT_EGRESS_MAX_VIOLATION_TOTAL="${CHAT_EGRESS_MAX_VIOLATION_TOTAL:-0}"
    CHAT_EGRESS_MAX_UNMASKED_SENSITIVE_TOTAL="${CHAT_EGRESS_MAX_UNMASKED_SENSITIVE_TOTAL:-0}"
    CHAT_EGRESS_MAX_UNKNOWN_DEST_TOTAL="${CHAT_EGRESS_MAX_UNKNOWN_DEST_TOTAL:-0}"
    CHAT_EGRESS_MAX_ERROR_RATIO="${CHAT_EGRESS_MAX_ERROR_RATIO:-0.05}"
    CHAT_EGRESS_MAX_MISSING_TRACE_TOTAL="${CHAT_EGRESS_MAX_MISSING_TRACE_TOTAL:-0}"
    CHAT_EGRESS_MIN_ALERT_COVERAGE_RATIO="${CHAT_EGRESS_MIN_ALERT_COVERAGE_RATIO:-1.0}"
    CHAT_EGRESS_MAX_STALE_MINUTES="${CHAT_EGRESS_MAX_STALE_MINUTES:-180}"

    $PYTHON_BIN "$ROOT_DIR/scripts/eval/chat_egress_guardrails_gate.py" \
      --events-jsonl "$CHAT_EGRESS_EVENTS_JSONL" \
      --allow-destinations "$CHAT_EGRESS_ALLOW_DESTINATIONS" \
      --window-hours "$CHAT_EGRESS_WINDOW_HOURS" \
      --limit "$CHAT_EGRESS_LIMIT" \
      --out "$CHAT_EGRESS_OUT_DIR" \
      --min-window "$CHAT_EGRESS_MIN_WINDOW" \
      --max-violation-total "$CHAT_EGRESS_MAX_VIOLATION_TOTAL" \
      --max-unmasked-sensitive-total "$CHAT_EGRESS_MAX_UNMASKED_SENSITIVE_TOTAL" \
      --max-unknown-destination-total "$CHAT_EGRESS_MAX_UNKNOWN_DEST_TOTAL" \
      --max-error-ratio "$CHAT_EGRESS_MAX_ERROR_RATIO" \
      --max-missing-trace-total "$CHAT_EGRESS_MAX_MISSING_TRACE_TOTAL" \
      --min-alert-coverage-ratio "$CHAT_EGRESS_MIN_ALERT_COVERAGE_RATIO" \
      --max-stale-minutes "$CHAT_EGRESS_MAX_STALE_MINUTES" \
      --gate || exit 1
  else
    echo "  - python not found; skipping chat egress guardrails gate"
  fi
else
  echo "  - set RUN_CHAT_EGRESS_GUARDRAILS_GATE=1 to enable"
fi

echo "[28/39] Chat data governance evidence gate (optional)"
if [ "${RUN_CHAT_DATA_GOV_EVIDENCE_GATE:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_DATA_GOV_REPORTS_DIR="${CHAT_DATA_GOV_REPORTS_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_DATA_GOV_RETENTION_PREFIX="${CHAT_DATA_GOV_RETENTION_PREFIX:-chat_data_retention_guard}"
    CHAT_DATA_GOV_EGRESS_PREFIX="${CHAT_DATA_GOV_EGRESS_PREFIX:-chat_egress_guardrails_gate}"
    CHAT_DATA_GOV_MIN_TRACE_COVERAGE="${CHAT_DATA_GOV_MIN_TRACE_COVERAGE:-1.0}"
    CHAT_DATA_GOV_MIN_SCORE="${CHAT_DATA_GOV_MIN_SCORE:-80}"
    CHAT_DATA_GOV_OUT_DIR="${CHAT_DATA_GOV_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_DATA_GOV_REQUIRE_REPORTS="${CHAT_DATA_GOV_REQUIRE_REPORTS:-0}"
    CHAT_DATA_GOV_REQUIRE_EVENTS="${CHAT_DATA_GOV_REQUIRE_EVENTS:-0}"
    CHAT_DATA_GOV_REQUIRE_READY="${CHAT_DATA_GOV_REQUIRE_READY:-0}"

    CHAT_DATA_GOV_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_data_governance_evidence.py"
      --reports-dir "$CHAT_DATA_GOV_REPORTS_DIR"
      --retention-prefix "$CHAT_DATA_GOV_RETENTION_PREFIX"
      --egress-prefix "$CHAT_DATA_GOV_EGRESS_PREFIX"
      --min-trace-coverage-ratio "$CHAT_DATA_GOV_MIN_TRACE_COVERAGE"
      --min-lifecycle-score "$CHAT_DATA_GOV_MIN_SCORE"
      --out "$CHAT_DATA_GOV_OUT_DIR"
      --gate
    )
    if [ "$CHAT_DATA_GOV_REQUIRE_REPORTS" = "1" ]; then
      CHAT_DATA_GOV_ARGS+=(--require-reports)
    fi
    if [ "$CHAT_DATA_GOV_REQUIRE_EVENTS" = "1" ]; then
      CHAT_DATA_GOV_ARGS+=(--require-events)
    fi
    if [ "$CHAT_DATA_GOV_REQUIRE_READY" = "1" ]; then
      CHAT_DATA_GOV_ARGS+=(--require-ready)
    fi
    $PYTHON_BIN "${CHAT_DATA_GOV_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat data governance evidence gate"
  fi
else
  echo "  - set RUN_CHAT_DATA_GOV_EVIDENCE_GATE=1 to enable"
fi

echo "[29/39] Chat load profile model gate (optional)"
if [ "${RUN_CHAT_LOAD_PROFILE_MODEL:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_LOAD_PROFILE_JSONL="${CHAT_LOAD_PROFILE_JSONL:-$ROOT_DIR/var/chat_governance/load_events.jsonl}"
    CHAT_LOAD_PROFILE_WINDOW_HOURS="${CHAT_LOAD_PROFILE_WINDOW_HOURS:-168}"
    CHAT_LOAD_PROFILE_LIMIT="${CHAT_LOAD_PROFILE_LIMIT:-50000}"
    CHAT_LOAD_PROFILE_OUT_DIR="${CHAT_LOAD_PROFILE_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_LOAD_PROFILE_MIN_WINDOW="${CHAT_LOAD_PROFILE_MIN_WINDOW:-0}"
    CHAT_LOAD_PROFILE_MAX_ERROR_RATIO="${CHAT_LOAD_PROFILE_MAX_ERROR_RATIO:-0.05}"
    CHAT_LOAD_PROFILE_MAX_P95_LATENCY_MS="${CHAT_LOAD_PROFILE_MAX_P95_LATENCY_MS:-3000}"
    CHAT_LOAD_PROFILE_MAX_P95_QUEUE_DEPTH="${CHAT_LOAD_PROFILE_MAX_P95_QUEUE_DEPTH:-50}"

    $PYTHON_BIN "$ROOT_DIR/scripts/eval/chat_load_profile_model.py" \
      --traffic-jsonl "$CHAT_LOAD_PROFILE_JSONL" \
      --window-hours "$CHAT_LOAD_PROFILE_WINDOW_HOURS" \
      --limit "$CHAT_LOAD_PROFILE_LIMIT" \
      --out "$CHAT_LOAD_PROFILE_OUT_DIR" \
      --min-window "$CHAT_LOAD_PROFILE_MIN_WINDOW" \
      --max-normal-error-ratio "$CHAT_LOAD_PROFILE_MAX_ERROR_RATIO" \
      --max-normal-p95-latency-ms "$CHAT_LOAD_PROFILE_MAX_P95_LATENCY_MS" \
      --max-normal-p95-queue-depth "$CHAT_LOAD_PROFILE_MAX_P95_QUEUE_DEPTH" \
      --gate || exit 1
  else
    echo "  - python not found; skipping chat load profile model gate"
  fi
else
  echo "  - set RUN_CHAT_LOAD_PROFILE_MODEL=1 to enable"
fi

echo "[30/39] Chat capacity forecast gate (optional)"
if [ "${RUN_CHAT_CAPACITY_FORECAST:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_FORECAST_REPORTS_DIR="${CHAT_FORECAST_REPORTS_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_FORECAST_LOAD_PREFIX="${CHAT_FORECAST_LOAD_PREFIX:-chat_load_profile_model}"
    CHAT_FORECAST_LOAD_REPORT="${CHAT_FORECAST_LOAD_REPORT:-}"
    CHAT_FORECAST_BASELINE_HOURS="${CHAT_FORECAST_BASELINE_HOURS:-168}"
    CHAT_FORECAST_WEEKLY_GROWTH="${CHAT_FORECAST_WEEKLY_GROWTH:-1.08}"
    CHAT_FORECAST_MONTHLY_GROWTH="${CHAT_FORECAST_MONTHLY_GROWTH:-1.35}"
    CHAT_FORECAST_PROMO_SURGE="${CHAT_FORECAST_PROMO_SURGE:-1.6}"
    CHAT_FORECAST_CPU_RPS_PER_CORE="${CHAT_FORECAST_CPU_RPS_PER_CORE:-3.0}"
    CHAT_FORECAST_GPU_TOKENS_PER_SEC="${CHAT_FORECAST_GPU_TOKENS_PER_SEC:-800}"
    CHAT_FORECAST_BASE_MEMORY_GB="${CHAT_FORECAST_BASE_MEMORY_GB:-2.0}"
    CHAT_FORECAST_MEMORY_PER_CORE_GB="${CHAT_FORECAST_MEMORY_PER_CORE_GB:-0.5}"
    CHAT_FORECAST_COST_PER_1K="${CHAT_FORECAST_COST_PER_1K:-0.002}"
    CHAT_FORECAST_OUT_DIR="${CHAT_FORECAST_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_FORECAST_MIN_WINDOW="${CHAT_FORECAST_MIN_WINDOW:-0}"
    CHAT_FORECAST_MAX_PEAK_RPS="${CHAT_FORECAST_MAX_PEAK_RPS:-50}"
    CHAT_FORECAST_MAX_MONTHLY_COST_USD="${CHAT_FORECAST_MAX_MONTHLY_COST_USD:-15000}"
    CHAT_FORECAST_MAX_CPU_CORES="${CHAT_FORECAST_MAX_CPU_CORES:-64}"
    CHAT_FORECAST_MAX_GPU_REQUIRED="${CHAT_FORECAST_MAX_GPU_REQUIRED:-8}"

    CHAT_FORECAST_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_capacity_forecast.py"
      --reports-dir "$CHAT_FORECAST_REPORTS_DIR"
      --load-prefix "$CHAT_FORECAST_LOAD_PREFIX"
      --baseline-window-hours "$CHAT_FORECAST_BASELINE_HOURS"
      --weekly-growth-factor "$CHAT_FORECAST_WEEKLY_GROWTH"
      --monthly-growth-factor "$CHAT_FORECAST_MONTHLY_GROWTH"
      --promo-surge-factor "$CHAT_FORECAST_PROMO_SURGE"
      --cpu-rps-per-core "$CHAT_FORECAST_CPU_RPS_PER_CORE"
      --gpu-tokens-per-sec "$CHAT_FORECAST_GPU_TOKENS_PER_SEC"
      --base-memory-gb "$CHAT_FORECAST_BASE_MEMORY_GB"
      --memory-per-core-gb "$CHAT_FORECAST_MEMORY_PER_CORE_GB"
      --cost-per-1k-tokens "$CHAT_FORECAST_COST_PER_1K"
      --out "$CHAT_FORECAST_OUT_DIR"
      --min-window "$CHAT_FORECAST_MIN_WINDOW"
      --max-peak-rps "$CHAT_FORECAST_MAX_PEAK_RPS"
      --max-monthly-cost-usd "$CHAT_FORECAST_MAX_MONTHLY_COST_USD"
      --max-cpu-cores "$CHAT_FORECAST_MAX_CPU_CORES"
      --max-gpu-required "$CHAT_FORECAST_MAX_GPU_REQUIRED"
      --gate
    )
    if [ -n "$CHAT_FORECAST_LOAD_REPORT" ]; then
      CHAT_FORECAST_ARGS+=(--load-report "$CHAT_FORECAST_LOAD_REPORT")
    fi
    $PYTHON_BIN "${CHAT_FORECAST_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat capacity forecast gate"
  fi
else
  echo "  - set RUN_CHAT_CAPACITY_FORECAST=1 to enable"
fi

echo "[31/39] Chat autoscaling calibration gate (optional)"
if [ "${RUN_CHAT_AUTOSCALING_CALIBRATION:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_AUTOSCALE_EVENTS_JSONL="${CHAT_AUTOSCALE_EVENTS_JSONL:-$ROOT_DIR/var/chat_governance/autoscaling_events.jsonl}"
    CHAT_AUTOSCALE_WINDOW_HOURS="${CHAT_AUTOSCALE_WINDOW_HOURS:-168}"
    CHAT_AUTOSCALE_LIMIT="${CHAT_AUTOSCALE_LIMIT:-50000}"
    CHAT_AUTOSCALE_REPORTS_DIR="${CHAT_AUTOSCALE_REPORTS_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_AUTOSCALE_FORECAST_PREFIX="${CHAT_AUTOSCALE_FORECAST_PREFIX:-chat_capacity_forecast}"
    CHAT_AUTOSCALE_FORECAST_REPORT="${CHAT_AUTOSCALE_FORECAST_REPORT:-}"
    CHAT_AUTOSCALE_UNDER_TOLERANCE="${CHAT_AUTOSCALE_UNDER_TOLERANCE:-0.05}"
    CHAT_AUTOSCALE_OVER_TOLERANCE="${CHAT_AUTOSCALE_OVER_TOLERANCE:-0.10}"
    CHAT_AUTOSCALE_BASE_PRESCALE="${CHAT_AUTOSCALE_BASE_PRESCALE:-1.20}"
    CHAT_AUTOSCALE_CAL_STEP="${CHAT_AUTOSCALE_CAL_STEP:-0.05}"
    CHAT_AUTOSCALE_OUT_DIR="${CHAT_AUTOSCALE_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_AUTOSCALE_MIN_WINDOW="${CHAT_AUTOSCALE_MIN_WINDOW:-0}"
    CHAT_AUTOSCALE_MAX_UNDER_RATIO="${CHAT_AUTOSCALE_MAX_UNDER_RATIO:-0.10}"
    CHAT_AUTOSCALE_MAX_OVER_RATIO="${CHAT_AUTOSCALE_MAX_OVER_RATIO:-0.35}"
    CHAT_AUTOSCALE_MAX_MAPE="${CHAT_AUTOSCALE_MAX_MAPE:-0.40}"
    CHAT_AUTOSCALE_MAX_CANARY_FAILURE="${CHAT_AUTOSCALE_MAX_CANARY_FAILURE:-0}"
    CHAT_AUTOSCALE_REQUIRE_RELEASE_CANARY="${CHAT_AUTOSCALE_REQUIRE_RELEASE_CANARY:-0}"

    CHAT_AUTOSCALE_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_autoscaling_calibration.py"
      --events-jsonl "$CHAT_AUTOSCALE_EVENTS_JSONL"
      --window-hours "$CHAT_AUTOSCALE_WINDOW_HOURS"
      --limit "$CHAT_AUTOSCALE_LIMIT"
      --reports-dir "$CHAT_AUTOSCALE_REPORTS_DIR"
      --capacity-forecast-prefix "$CHAT_AUTOSCALE_FORECAST_PREFIX"
      --under-tolerance-ratio "$CHAT_AUTOSCALE_UNDER_TOLERANCE"
      --over-tolerance-ratio "$CHAT_AUTOSCALE_OVER_TOLERANCE"
      --base-prescale-factor "$CHAT_AUTOSCALE_BASE_PRESCALE"
      --calibration-step "$CHAT_AUTOSCALE_CAL_STEP"
      --out "$CHAT_AUTOSCALE_OUT_DIR"
      --min-window "$CHAT_AUTOSCALE_MIN_WINDOW"
      --max-under-ratio "$CHAT_AUTOSCALE_MAX_UNDER_RATIO"
      --max-over-ratio "$CHAT_AUTOSCALE_MAX_OVER_RATIO"
      --max-prediction-mape "$CHAT_AUTOSCALE_MAX_MAPE"
      --max-canary-failure-total "$CHAT_AUTOSCALE_MAX_CANARY_FAILURE"
      --gate
    )
    if [ -n "$CHAT_AUTOSCALE_FORECAST_REPORT" ]; then
      CHAT_AUTOSCALE_ARGS+=(--capacity-forecast-report "$CHAT_AUTOSCALE_FORECAST_REPORT")
    fi
    if [ "$CHAT_AUTOSCALE_REQUIRE_RELEASE_CANARY" = "1" ]; then
      CHAT_AUTOSCALE_ARGS+=(--require-release-canary)
    fi
    $PYTHON_BIN "${CHAT_AUTOSCALE_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat autoscaling calibration gate"
  fi
else
  echo "  - set RUN_CHAT_AUTOSCALING_CALIBRATION=1 to enable"
fi

echo "[32/39] Chat session gateway durability gate (optional)"
if [ "${RUN_CHAT_SESSION_DURABILITY_GATE:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_SESSION_DURABILITY_EVENTS_JSONL="${CHAT_SESSION_DURABILITY_EVENTS_JSONL:-$ROOT_DIR/var/chat_governance/session_gateway_events.jsonl}"
    CHAT_SESSION_DURABILITY_WINDOW_HOURS="${CHAT_SESSION_DURABILITY_WINDOW_HOURS:-24}"
    CHAT_SESSION_DURABILITY_LIMIT="${CHAT_SESSION_DURABILITY_LIMIT:-50000}"
    CHAT_SESSION_DURABILITY_HEARTBEAT_LAG_MS="${CHAT_SESSION_DURABILITY_HEARTBEAT_LAG_MS:-30000}"
    CHAT_SESSION_DURABILITY_OUT_DIR="${CHAT_SESSION_DURABILITY_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_SESSION_DURABILITY_MIN_WINDOW="${CHAT_SESSION_DURABILITY_MIN_WINDOW:-0}"
    CHAT_SESSION_DURABILITY_MIN_RECONNECT_SUCCESS="${CHAT_SESSION_DURABILITY_MIN_RECONNECT_SUCCESS:-0.95}"
    CHAT_SESSION_DURABILITY_MIN_RESUME_SUCCESS="${CHAT_SESSION_DURABILITY_MIN_RESUME_SUCCESS:-0.98}"
    CHAT_SESSION_DURABILITY_MAX_HEARTBEAT_MISS="${CHAT_SESSION_DURABILITY_MAX_HEARTBEAT_MISS:-0.05}"
    CHAT_SESSION_DURABILITY_MAX_AFFINITY_MISS="${CHAT_SESSION_DURABILITY_MAX_AFFINITY_MISS:-0.02}"
    CHAT_SESSION_DURABILITY_MAX_STALE_MINUTES="${CHAT_SESSION_DURABILITY_MAX_STALE_MINUTES:-60}"

    $PYTHON_BIN "$ROOT_DIR/scripts/eval/chat_session_gateway_durability.py" \
      --events-jsonl "$CHAT_SESSION_DURABILITY_EVENTS_JSONL" \
      --window-hours "$CHAT_SESSION_DURABILITY_WINDOW_HOURS" \
      --limit "$CHAT_SESSION_DURABILITY_LIMIT" \
      --heartbeat-lag-threshold-ms "$CHAT_SESSION_DURABILITY_HEARTBEAT_LAG_MS" \
      --out "$CHAT_SESSION_DURABILITY_OUT_DIR" \
      --min-window "$CHAT_SESSION_DURABILITY_MIN_WINDOW" \
      --min-reconnect-success-rate "$CHAT_SESSION_DURABILITY_MIN_RECONNECT_SUCCESS" \
      --min-resume-success-rate "$CHAT_SESSION_DURABILITY_MIN_RESUME_SUCCESS" \
      --max-heartbeat-miss-ratio "$CHAT_SESSION_DURABILITY_MAX_HEARTBEAT_MISS" \
      --max-affinity-miss-ratio "$CHAT_SESSION_DURABILITY_MAX_AFFINITY_MISS" \
      --max-stale-minutes "$CHAT_SESSION_DURABILITY_MAX_STALE_MINUTES" \
      --gate || exit 1
  else
    echo "  - python not found; skipping chat session gateway durability gate"
  fi
else
  echo "  - set RUN_CHAT_SESSION_DURABILITY_GATE=1 to enable"
fi

echo "[33/39] Chat event delivery guarantee gate (optional)"
if [ "${RUN_CHAT_EVENT_DELIVERY_GUARANTEE:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_EVENT_DELIVERY_EVENTS_JSONL="${CHAT_EVENT_DELIVERY_EVENTS_JSONL:-$ROOT_DIR/var/chat_governance/event_delivery_events.jsonl}"
    CHAT_EVENT_DELIVERY_WINDOW_HOURS="${CHAT_EVENT_DELIVERY_WINDOW_HOURS:-24}"
    CHAT_EVENT_DELIVERY_LIMIT="${CHAT_EVENT_DELIVERY_LIMIT:-50000}"
    CHAT_EVENT_DELIVERY_OUT_DIR="${CHAT_EVENT_DELIVERY_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_EVENT_DELIVERY_MIN_WINDOW="${CHAT_EVENT_DELIVERY_MIN_WINDOW:-0}"
    CHAT_EVENT_DELIVERY_MIN_SUCCESS_RATIO="${CHAT_EVENT_DELIVERY_MIN_SUCCESS_RATIO:-0.99}"
    CHAT_EVENT_DELIVERY_MAX_ORDER_VIOLATIONS="${CHAT_EVENT_DELIVERY_MAX_ORDER_VIOLATIONS:-0}"
    CHAT_EVENT_DELIVERY_MAX_DUPLICATE_RATIO="${CHAT_EVENT_DELIVERY_MAX_DUPLICATE_RATIO:-0.01}"
    CHAT_EVENT_DELIVERY_MAX_ACK_MISSING_RATIO="${CHAT_EVENT_DELIVERY_MAX_ACK_MISSING_RATIO:-0.02}"
    CHAT_EVENT_DELIVERY_MAX_SYNC_GAP="${CHAT_EVENT_DELIVERY_MAX_SYNC_GAP:-5}"
    CHAT_EVENT_DELIVERY_MAX_TTL_DROP_TOTAL="${CHAT_EVENT_DELIVERY_MAX_TTL_DROP_TOTAL:-0}"
    CHAT_EVENT_DELIVERY_MAX_STALE_MINUTES="${CHAT_EVENT_DELIVERY_MAX_STALE_MINUTES:-60}"

    $PYTHON_BIN "$ROOT_DIR/scripts/eval/chat_event_delivery_guarantee.py" \
      --events-jsonl "$CHAT_EVENT_DELIVERY_EVENTS_JSONL" \
      --window-hours "$CHAT_EVENT_DELIVERY_WINDOW_HOURS" \
      --limit "$CHAT_EVENT_DELIVERY_LIMIT" \
      --out "$CHAT_EVENT_DELIVERY_OUT_DIR" \
      --min-window "$CHAT_EVENT_DELIVERY_MIN_WINDOW" \
      --min-delivery-success-ratio "$CHAT_EVENT_DELIVERY_MIN_SUCCESS_RATIO" \
      --max-order-violation-total "$CHAT_EVENT_DELIVERY_MAX_ORDER_VIOLATIONS" \
      --max-duplicate-ratio "$CHAT_EVENT_DELIVERY_MAX_DUPLICATE_RATIO" \
      --max-ack-missing-ratio "$CHAT_EVENT_DELIVERY_MAX_ACK_MISSING_RATIO" \
      --max-sync-gap "$CHAT_EVENT_DELIVERY_MAX_SYNC_GAP" \
      --max-ttl-drop-total "$CHAT_EVENT_DELIVERY_MAX_TTL_DROP_TOTAL" \
      --max-stale-minutes "$CHAT_EVENT_DELIVERY_MAX_STALE_MINUTES" \
      --gate || exit 1
  else
    echo "  - python not found; skipping chat event delivery guarantee gate"
  fi
else
  echo "  - set RUN_CHAT_EVENT_DELIVERY_GUARANTEE=1 to enable"
fi

echo "[34/39] Chat backpressure admission guard (optional)"
if [ "${RUN_CHAT_BACKPRESSURE_ADMISSION_GUARD:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_BACKPRESSURE_EVENTS_JSONL="${CHAT_BACKPRESSURE_EVENTS_JSONL:-$ROOT_DIR/var/chat_governance/backpressure_events.jsonl}"
    CHAT_BACKPRESSURE_WINDOW_HOURS="${CHAT_BACKPRESSURE_WINDOW_HOURS:-24}"
    CHAT_BACKPRESSURE_LIMIT="${CHAT_BACKPRESSURE_LIMIT:-50000}"
    CHAT_BACKPRESSURE_OUT_DIR="${CHAT_BACKPRESSURE_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_BACKPRESSURE_MIN_WINDOW="${CHAT_BACKPRESSURE_MIN_WINDOW:-0}"
    CHAT_BACKPRESSURE_MAX_DROP_RATIO="${CHAT_BACKPRESSURE_MAX_DROP_RATIO:-0.20}"
    CHAT_BACKPRESSURE_MAX_CRITICAL_DROP_TOTAL="${CHAT_BACKPRESSURE_MAX_CRITICAL_DROP_TOTAL:-0}"
    CHAT_BACKPRESSURE_MIN_CORE_PROTECTED_RATIO="${CHAT_BACKPRESSURE_MIN_CORE_PROTECTED_RATIO:-0.98}"
    CHAT_BACKPRESSURE_MAX_P95_QUEUE_DEPTH="${CHAT_BACKPRESSURE_MAX_P95_QUEUE_DEPTH:-80}"
    CHAT_BACKPRESSURE_MAX_P95_QUEUE_LATENCY_MS="${CHAT_BACKPRESSURE_MAX_P95_QUEUE_LATENCY_MS:-3000}"
    CHAT_BACKPRESSURE_MAX_GUIDANCE_MISSING_TOTAL="${CHAT_BACKPRESSURE_MAX_GUIDANCE_MISSING_TOTAL:-0}"
    CHAT_BACKPRESSURE_MAX_STALE_MINUTES="${CHAT_BACKPRESSURE_MAX_STALE_MINUTES:-60}"

    $PYTHON_BIN "$ROOT_DIR/scripts/eval/chat_backpressure_admission_guard.py" \
      --events-jsonl "$CHAT_BACKPRESSURE_EVENTS_JSONL" \
      --window-hours "$CHAT_BACKPRESSURE_WINDOW_HOURS" \
      --limit "$CHAT_BACKPRESSURE_LIMIT" \
      --out "$CHAT_BACKPRESSURE_OUT_DIR" \
      --min-window "$CHAT_BACKPRESSURE_MIN_WINDOW" \
      --max-drop-ratio "$CHAT_BACKPRESSURE_MAX_DROP_RATIO" \
      --max-critical-drop-total "$CHAT_BACKPRESSURE_MAX_CRITICAL_DROP_TOTAL" \
      --min-core-protected-ratio "$CHAT_BACKPRESSURE_MIN_CORE_PROTECTED_RATIO" \
      --max-p95-queue-depth "$CHAT_BACKPRESSURE_MAX_P95_QUEUE_DEPTH" \
      --max-p95-queue-latency-ms "$CHAT_BACKPRESSURE_MAX_P95_QUEUE_LATENCY_MS" \
      --max-guidance-missing-total "$CHAT_BACKPRESSURE_MAX_GUIDANCE_MISSING_TOTAL" \
      --max-stale-minutes "$CHAT_BACKPRESSURE_MAX_STALE_MINUTES" \
      --gate || exit 1
  else
    echo "  - python not found; skipping chat backpressure admission guard"
  fi
else
  echo "  - set RUN_CHAT_BACKPRESSURE_ADMISSION_GUARD=1 to enable"
fi

echo "[35/39] Chat session resilience drill report gate (optional)"
if [ "${RUN_CHAT_SESSION_RESILIENCE_DRILL_REPORT:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_SESSION_DRILL_EVENTS_JSONL="${CHAT_SESSION_DRILL_EVENTS_JSONL:-$ROOT_DIR/var/chat_governance/session_resilience_drills.jsonl}"
    CHAT_SESSION_DRILL_WINDOW_DAYS="${CHAT_SESSION_DRILL_WINDOW_DAYS:-30}"
    CHAT_SESSION_DRILL_LIMIT="${CHAT_SESSION_DRILL_LIMIT:-50000}"
    CHAT_SESSION_DRILL_REQUIRED_SCENARIOS="${CHAT_SESSION_DRILL_REQUIRED_SCENARIOS:-CONNECTION_STORM,PARTIAL_REGION_FAIL,BROKER_DELAY}"
    CHAT_SESSION_DRILL_OUT_DIR="${CHAT_SESSION_DRILL_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_SESSION_DRILL_MIN_WINDOW="${CHAT_SESSION_DRILL_MIN_WINDOW:-0}"
    CHAT_SESSION_DRILL_MAX_OPEN_TOTAL="${CHAT_SESSION_DRILL_MAX_OPEN_TOTAL:-0}"
    CHAT_SESSION_DRILL_MAX_AVG_RTO_SEC="${CHAT_SESSION_DRILL_MAX_AVG_RTO_SEC:-900}"
    CHAT_SESSION_DRILL_MAX_LOSS_RATIO="${CHAT_SESSION_DRILL_MAX_LOSS_RATIO:-0.001}"
    CHAT_SESSION_DRILL_MAX_STALE_DAYS="${CHAT_SESSION_DRILL_MAX_STALE_DAYS:-35}"
    CHAT_SESSION_DRILL_REQUIRE_SCENARIOS="${CHAT_SESSION_DRILL_REQUIRE_SCENARIOS:-0}"

    CHAT_SESSION_DRILL_ARGS=(
      "$ROOT_DIR/scripts/eval/chat_session_resilience_drill_report.py"
      --events-jsonl "$CHAT_SESSION_DRILL_EVENTS_JSONL"
      --window-days "$CHAT_SESSION_DRILL_WINDOW_DAYS"
      --limit "$CHAT_SESSION_DRILL_LIMIT"
      --required-scenarios "$CHAT_SESSION_DRILL_REQUIRED_SCENARIOS"
      --out "$CHAT_SESSION_DRILL_OUT_DIR"
      --min-window "$CHAT_SESSION_DRILL_MIN_WINDOW"
      --max-open-drill-total "$CHAT_SESSION_DRILL_MAX_OPEN_TOTAL"
      --max-avg-rto-sec "$CHAT_SESSION_DRILL_MAX_AVG_RTO_SEC"
      --max-message-loss-ratio "$CHAT_SESSION_DRILL_MAX_LOSS_RATIO"
      --max-stale-days "$CHAT_SESSION_DRILL_MAX_STALE_DAYS"
      --gate
    )
    if [ "$CHAT_SESSION_DRILL_REQUIRE_SCENARIOS" = "1" ]; then
      CHAT_SESSION_DRILL_ARGS+=(--require-scenarios)
    fi
    $PYTHON_BIN "${CHAT_SESSION_DRILL_ARGS[@]}" || exit 1
  else
    echo "  - python not found; skipping chat session resilience drill report gate"
  fi
else
  echo "  - set RUN_CHAT_SESSION_RESILIENCE_DRILL_REPORT=1 to enable"
fi

echo "[36/39] Chat unit economics SLO gate (optional)"
if [ "${RUN_CHAT_UNIT_ECONOMICS_SLO:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    CHAT_UNIT_ECON_EVENTS_JSONL="${CHAT_UNIT_ECON_EVENTS_JSONL:-$ROOT_DIR/var/chat_finops/session_cost_events.jsonl}"
    CHAT_UNIT_ECON_WINDOW_DAYS="${CHAT_UNIT_ECON_WINDOW_DAYS:-7}"
    CHAT_UNIT_ECON_LIMIT="${CHAT_UNIT_ECON_LIMIT:-100000}"
    CHAT_UNIT_ECON_OUT_DIR="${CHAT_UNIT_ECON_OUT_DIR:-$ROOT_DIR/data/eval/reports}"
    CHAT_UNIT_ECON_MIN_WINDOW="${CHAT_UNIT_ECON_MIN_WINDOW:-0}"
    CHAT_UNIT_ECON_MIN_RESOLUTION_RATE="${CHAT_UNIT_ECON_MIN_RESOLUTION_RATE:-0.80}"
    CHAT_UNIT_ECON_MAX_COST_PER_RESOLVED="${CHAT_UNIT_ECON_MAX_COST_PER_RESOLVED:-2.0}"
    CHAT_UNIT_ECON_MAX_UNRESOLVED_BURN="${CHAT_UNIT_ECON_MAX_UNRESOLVED_BURN:-200}"
    CHAT_UNIT_ECON_MAX_TOOL_MIX="${CHAT_UNIT_ECON_MAX_TOOL_MIX:-0.80}"
    CHAT_UNIT_ECON_MAX_STALE_DAYS="${CHAT_UNIT_ECON_MAX_STALE_DAYS:-8}"

    $PYTHON_BIN "$ROOT_DIR/scripts/eval/chat_unit_economics_slo.py" \
      --events-jsonl "$CHAT_UNIT_ECON_EVENTS_JSONL" \
      --window-days "$CHAT_UNIT_ECON_WINDOW_DAYS" \
      --limit "$CHAT_UNIT_ECON_LIMIT" \
      --out "$CHAT_UNIT_ECON_OUT_DIR" \
      --min-window "$CHAT_UNIT_ECON_MIN_WINDOW" \
      --min-resolution-rate "$CHAT_UNIT_ECON_MIN_RESOLUTION_RATE" \
      --max-cost-per-resolved-session "$CHAT_UNIT_ECON_MAX_COST_PER_RESOLVED" \
      --max-unresolved-cost-burn-total "$CHAT_UNIT_ECON_MAX_UNRESOLVED_BURN" \
      --max-tool-cost-mix-ratio "$CHAT_UNIT_ECON_MAX_TOOL_MIX" \
      --max-stale-days "$CHAT_UNIT_ECON_MAX_STALE_DAYS" \
      --gate || exit 1
  else
    echo "  - python not found; skipping chat unit economics SLO gate"
  fi
else
  echo "  - set RUN_CHAT_UNIT_ECONOMICS_SLO=1 to enable"
fi

echo "[37/39] Canonical quality checks (optional)"
if [ "${RUN_CANONICAL_CHECKS:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    $PYTHON_BIN "$ROOT_DIR/scripts/canonical/validate_canonical.py" || exit 1
  else
    echo "  - python not found; skipping canonical checks"
  fi
else
  echo "  - set RUN_CANONICAL_CHECKS=1 to enable"
fi

echo "[38/39] E2E tests (optional)"
if [ "${RUN_E2E:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    $PYTHON_BIN "$ROOT_DIR/scripts/e2e/e2e_commerce_flow.py" || exit 1
  else
    echo "  - python not found; skipping E2E"
  fi
else
  echo "  - set RUN_E2E=1 to enable"
fi

echo "[39/39] Done"
