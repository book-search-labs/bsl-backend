#!/usr/bin/env bash
set -euo pipefail

echo "[1/2] Contract validation (optional)"
if command -v python >/dev/null 2>&1; then
  if python -c "import jsonschema" >/dev/null 2>&1; then
    python scripts/validate_contracts.py
  else
    echo "  - python jsonschema not found; skipping (install: python -m pip install jsonschema)"
  fi
else
  echo "  - python not found; skipping contract validation"
fi

echo "[2/2] Done"
