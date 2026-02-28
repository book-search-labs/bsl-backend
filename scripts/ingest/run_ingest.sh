#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

DATA_ROOT="${NLK_DATA_DIR:-$ROOT_DIR/data/nlk}"
RAW_DIR="$DATA_ROOT/raw"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
INSTALL_DEPS="${INSTALL_DEPS:-0}"
INGEST_TARGETS="${INGEST_TARGETS:-mysql,opensearch}"
NLK_INPUT_MODE="${NLK_INPUT_MODE:-sample}"
RAW_NODE_SYNC="${RAW_NODE_SYNC:-1}"
BOOTSTRAP_OS="${BOOTSTRAP_OS:-1}"
OS_URL="${OS_URL:-http://localhost:9200}"
FAST_MODE="${FAST_MODE:-0}"

case "$NLK_INPUT_MODE" in
  sample|full|all)
    ;;
  *)
    echo "Unsupported NLK_INPUT_MODE: $NLK_INPUT_MODE (use sample|full|all)" >&2
    exit 1
    ;;
esac
export NLK_INPUT_MODE

if [ "$FAST_MODE" = "1" ]; then
  : "${MYSQL_BATCH_SIZE:=20000}"
  : "${MYSQL_CHUNK_SIZE:=2000}"
  : "${MYSQL_PROGRESS_EVERY:=50000}"
  : "${OS_BULK_SIZE:=5000}"
  : "${OS_TIMEOUT_SEC:=30}"
  : "${ENABLE_ENTITY_INDICES:=0}"
  : "${RAW_HASH_MODE:=record_id}"
  : "${STORE_BIBLIO_RAW:=0}"
  : "${MYSQL_BULK_MODE:=1}"
  : "${MYSQL_LOAD_BATCH:=100000}"
  export MYSQL_BATCH_SIZE MYSQL_CHUNK_SIZE MYSQL_PROGRESS_EVERY
  export OS_BULK_SIZE OS_TIMEOUT_SEC ENABLE_ENTITY_INDICES
  export RAW_HASH_MODE STORE_BIBLIO_RAW
  export MYSQL_BULK_MODE MYSQL_LOAD_BATCH
fi

if [ "$NLK_INPUT_MODE" = "sample" ] && [ -z "${EMBED_PROVIDER:-}" ] && [ -z "${MIS_URL:-}" ]; then
  export EMBED_PROVIDER="toy"
fi
if [ "${EMBED_PROVIDER:-}" = "toy" ] && [ -z "${EMBED_DIM:-}" ]; then
  export EMBED_DIM="384"
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required for NLK ingestion. Install Python 3 and retry." >&2
  exit 1
fi

if [ ! -d "$RAW_DIR" ]; then
  echo "Raw data directory not found: $RAW_DIR" >&2
  echo "Set NLK_DATA_DIR or place raw files under ./data/nlk/raw." >&2
  exit 1
fi

check_python_deps() {
  python3 - <<'PY'
import importlib
missing = []
for name in ("pymysql", "ijson", "cryptography"):
    try:
        importlib.import_module(name)
    except Exception:
        missing.append(name)
if missing:
    print("Missing Python deps: " + ", ".join(missing))
    raise SystemExit(1)
PY
}

if ! check_python_deps; then
  if [ "$INSTALL_DEPS" = "1" ]; then
    echo "Installing Python dependencies..."
    python3 -m pip install -r "$REQUIREMENTS_FILE"
    check_python_deps
  else
    echo "Install Python deps with: python3 -m pip install -r $REQUIREMENTS_FILE" >&2
    echo "Or rerun with INSTALL_DEPS=1 to auto-install." >&2
    exit 1
  fi
fi

echo "NLK input mode: $NLK_INPUT_MODE"
if [ "${EMBED_PROVIDER:-}" != "" ]; then
  echo "Embedding provider: ${EMBED_PROVIDER}"
fi
echo "Raw-node sync: $RAW_NODE_SYNC"

alias_exists() {
  local alias_name="$1"
  local code
  code="$(curl -s -o /dev/null -w "%{http_code}" "$OS_URL/_alias/$alias_name")"
  [ "$code" = "200" ]
}

bootstrap_opensearch_if_needed() {
  if [ "$BOOTSTRAP_OS" = "0" ]; then
    return 0
  fi
  if alias_exists "books_doc_write" && alias_exists "ac_write"; then
    return 0
  fi
  echo "Bootstrapping OpenSearch indices/aliases (KEEP_INDEX=1)..."
  OS_URL="$OS_URL" KEEP_INDEX=1 "$ROOT_DIR/scripts/os_bootstrap_indices_v1_1.sh"
}

IFS=',' read -r -a targets <<< "$INGEST_TARGETS"
for target in "${targets[@]}"; do
  trimmed="${target// /}"
  case "$trimmed" in
    mysql)
      echo "Starting MySQL ingestion..."
      python3 "$SCRIPT_DIR/ingest_mysql.py"
      if [ "$RAW_NODE_SYNC" = "1" ]; then
        echo "Syncing nlk_raw_nodes -> raw_node..."
        python3 "$SCRIPT_DIR/sync_raw_node.py"
      fi
      ;;
    opensearch)
      bootstrap_opensearch_if_needed
      echo "Starting OpenSearch ingestion..."
      python3 "$SCRIPT_DIR/ingest_opensearch.py"
      ;;
    "")
      ;;
    *)
      echo "Unknown INGEST_TARGETS entry: $trimmed" >&2
      exit 1
      ;;
  esac
done
