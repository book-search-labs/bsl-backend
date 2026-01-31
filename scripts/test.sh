#!/usr/bin/env bash
set -euo pipefail

echo "[1/7] Contract validation (optional)"
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

echo "[2/7] Contract compatibility gate (optional)"
if [ -n "$PYTHON_BIN" ]; then
  $PYTHON_BIN "$ROOT_DIR/scripts/contract_compat_check.py" || exit 1
else
  echo "  - python not found; skipping contract compatibility check"
fi

echo "[3/7] Feature spec validation (optional)"
if [ -n "$PYTHON_BIN" ]; then
  if $PYTHON_BIN -c "import yaml" >/dev/null 2>&1; then
    $PYTHON_BIN "$ROOT_DIR/scripts/validate_feature_spec.py" || exit 1
  else
    echo "  - PyYAML not found; skipping (install: $PYTHON_BIN -m pip install pyyaml)"
  fi
else
  echo "  - python not found; skipping feature spec validation"
fi

echo "[4/7] Offline eval gate (optional)"
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

echo "[5/7] Canonical quality checks (optional)"
if [ "${RUN_CANONICAL_CHECKS:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    $PYTHON_BIN "$ROOT_DIR/scripts/canonical/validate_canonical.py" || exit 1
  else
    echo "  - python not found; skipping canonical checks"
  fi
else
  echo "  - set RUN_CANONICAL_CHECKS=1 to enable"
fi

echo "[6/7] E2E tests (optional)"
if [ "${RUN_E2E:-0}" = "1" ]; then
  if [ -n "$PYTHON_BIN" ]; then
    $PYTHON_BIN "$ROOT_DIR/scripts/e2e/e2e_commerce_flow.py" || exit 1
  else
    echo "  - python not found; skipping E2E"
  fi
else
  echo "  - set RUN_E2E=1 to enable"
fi

echo "[7/7] Done"
