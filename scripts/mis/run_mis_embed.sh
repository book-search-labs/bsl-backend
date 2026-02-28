#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODEL_DIR="${MIS_EMBED_MODEL_DIR:-$ROOT_DIR/models/embed/bge-m3}"
MIS_HOST="${MIS_HOST:-0.0.0.0}"
MIS_PORT="${MIS_PORT:-8005}"

export MIS_EMBED_BACKEND="${MIS_EMBED_BACKEND:-onnx}"
export MIS_EMBED_MODEL_ID="${MIS_EMBED_MODEL_ID:-bge-m3}"
export MIS_DEFAULT_EMBED_MODEL="${MIS_DEFAULT_EMBED_MODEL:-$MIS_EMBED_MODEL_ID}"
export MIS_EMBED_MODEL_PATH="${MIS_EMBED_MODEL_PATH:-$MODEL_DIR/model.onnx}"
export MIS_EMBED_TOKENIZER_PATH="${MIS_EMBED_TOKENIZER_PATH:-$MODEL_DIR/tokenizer.json}"
export MIS_EMBED_NORMALIZE="${MIS_EMBED_NORMALIZE:-true}"
export MIS_MODEL_DIR="${MIS_MODEL_DIR:-$ROOT_DIR/models}"

if [[ "$MIS_EMBED_BACKEND" != "onnx" ]]; then
  echo "[ERROR] run_mis_embed.sh requires MIS_EMBED_BACKEND=onnx" >&2
  exit 1
fi

if [[ ! -f "$MIS_EMBED_MODEL_PATH" || ! -f "$MIS_EMBED_TOKENIZER_PATH" ]]; then
  echo "[ERROR] embed model artifacts missing" >&2
  echo "  model: $MIS_EMBED_MODEL_PATH" >&2
  echo "  tokenizer: $MIS_EMBED_TOKENIZER_PATH" >&2
  echo "Required files: model.onnx, tokenizer.json" >&2
  exit 1
fi

if ! python3 - <<'PY' >/dev/null 2>&1
import importlib
importlib.import_module("onnxruntime")
importlib.import_module("tokenizers")
PY
then
  echo "[ERROR] missing python dependencies for ONNX embed backend" >&2
  echo "Install with: pip install -r services/model-inference-service/requirements.txt" >&2
  exit 1
fi

echo "[OK] starting MIS with embed backend=onnx model_id=$MIS_EMBED_MODEL_ID"
cd "$ROOT_DIR/services/model-inference-service"
python3 -m uvicorn app.main:app --host "$MIS_HOST" --port "$MIS_PORT" --reload
