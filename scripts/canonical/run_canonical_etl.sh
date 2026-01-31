#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

BATCH_ID="${BATCH_ID:-}"
BATCH_SIZE="${BATCH_SIZE:-1000}"
ENTITY_KINDS="${ENTITY_KINDS:-CONCEPT,AGENT,LIBRARY,MATERIAL}"
MAX_BATCHES="${MAX_BATCHES:-}"
RUN_QUALITY="${RUN_QUALITY:-1}"
RUN_AUTHORITY="${RUN_AUTHORITY:-0}"
RULE_VERSION="${RULE_VERSION:-v1}"
SINCE_DATE="${SINCE_DATE:-}"
MAX_MATERIALS="${MAX_MATERIALS:-}"

PYTHON_BIN=""
if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

if [ -z "$PYTHON_BIN" ]; then
  echo "python3 is required for canonical ETL." >&2
  exit 1
fi

ETL_ARGS=("$SCRIPT_DIR/canonical_etl.py" "--batch-size" "$BATCH_SIZE" "--entity-kinds" "$ENTITY_KINDS")
if [ -n "$BATCH_ID" ]; then
  ETL_ARGS+=("--batch-id" "$BATCH_ID")
fi
if [ -n "$MAX_BATCHES" ]; then
  ETL_ARGS+=("--max-batches" "$MAX_BATCHES")
fi

$PYTHON_BIN "${ETL_ARGS[@]}"

if [ "$RUN_QUALITY" = "1" ]; then
  $PYTHON_BIN "$SCRIPT_DIR/validate_canonical.py"
fi

if [ "$RUN_AUTHORITY" = "1" ]; then
  AUTH_ARGS=("$ROOT_DIR/scripts/authority/build_candidates.py" "--rule-version" "$RULE_VERSION")
  if [ -n "$SINCE_DATE" ]; then
    AUTH_ARGS+=("--since-date" "$SINCE_DATE")
  fi
  if [ -n "$MAX_MATERIALS" ]; then
    AUTH_ARGS+=("--max-materials" "$MAX_MATERIALS")
  fi
  $PYTHON_BIN "${AUTH_ARGS[@]}"
fi
