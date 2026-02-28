#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODEL_DIR="${MIS_EMBED_MODEL_DIR:-$ROOT_DIR/models/embed/bge-m3}"
BASE_URL="${BGE_M3_BASE_URL:-https://huggingface.co/BAAI/bge-m3/resolve/main/onnx}"

files=(
  "model.onnx"
  "model.onnx_data"
  "Constant_7_attr__value"
  "tokenizer.json"
)

if ! command -v curl >/dev/null 2>&1; then
  echo "[ERROR] curl is required" >&2
  exit 1
fi

mkdir -p "$MODEL_DIR"

curl_args=(-fL --retry 3 --retry-delay 2 --continue-at -)
if [[ -n "${HF_TOKEN:-}" ]]; then
  curl_args+=(-H "Authorization: Bearer ${HF_TOKEN}")
fi

for file in "${files[@]}"; do
  url="${BASE_URL}/${file}"
  out="${MODEL_DIR}/${file}"
  echo "[DOWNLOAD] ${file}"
  curl "${curl_args[@]}" "$url" -o "$out"
  if [[ ! -s "$out" ]]; then
    echo "[ERROR] empty file downloaded: $out" >&2
    exit 1
  fi
done

echo "[OK] bge-m3 ONNX artifacts downloaded to: $MODEL_DIR"
echo "Next: ./scripts/mis/run_mis_embed.sh"
