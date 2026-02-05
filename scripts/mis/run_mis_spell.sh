#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODEL_DIR="${MIS_SPELL_MODEL_DIR:-$ROOT_DIR/models/spell/t5-typo-ko-v1}"
MIS_HOST="${MIS_HOST:-0.0.0.0}"
MIS_PORT="${MIS_PORT:-8005}"

export MIS_SPELL_ENABLE="true"
export MIS_SPELL_BACKEND="onnx"
export MIS_SPELL_MODEL_ID="${MIS_SPELL_MODEL_ID:-t5-typo-ko-v1}"
export MIS_SPELL_MODEL_PATH="${MODEL_DIR}/spell.onnx"
export MIS_SPELL_TOKENIZER_PATH="${MODEL_DIR}/tokenizer.json"
export MIS_SPELL_FALLBACK="${MIS_SPELL_FALLBACK:-error}"
export MIS_MODEL_DIR="${MIS_MODEL_DIR:-$ROOT_DIR/models}"

if [[ ! -f "$MIS_SPELL_MODEL_PATH" || ! -f "$MIS_SPELL_TOKENIZER_PATH" ]]; then
  echo "[ERROR] spell model artifacts missing at $MODEL_DIR" >&2
  echo "Required files: spell.onnx, tokenizer.json" >&2
  exit 1
fi

echo "[OK] starting MIS with spell backend=onnx model_id=$MIS_SPELL_MODEL_ID"
cd "$ROOT_DIR/services/model-inference-service"
python3 -m uvicorn app.main:app --host "$MIS_HOST" --port "$MIS_PORT" --reload
