#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/compose.yaml"

NLK_INPUT_MODE="${NLK_INPUT_MODE:-sample}"
FAST_MODE="${FAST_MODE:-1}"
INSTALL_DEPS="${INSTALL_DEPS:-0}"
EMBED_PROVIDER="${EMBED_PROVIDER:-toy}"
INGEST_TARGETS="${INGEST_TARGETS:-mysql,opensearch}"
RAW_NODE_SYNC="${RAW_NODE_SYNC:-1}"
RUN_KDC_SEED="${RUN_KDC_SEED:-1}"

if [ "$NLK_INPUT_MODE" != "sample" ]; then
  echo "local_reset_sample_data.sh requires NLK_INPUT_MODE=sample (current: $NLK_INPUT_MODE)." >&2
  exit 1
fi

echo "1/2 Resetting local docker volumes (MySQL/OpenSearch)..."
KEEP_VOLUME=0 "$SCRIPT_DIR/local_down.sh"

echo "2/2 Running sample bootstrap (compose up -> Flyway V2 -> ingest -> Flyway V3+)..."
INGEST_INSTALL_DEPS="$INSTALL_DEPS" \
FAST_MODE="$FAST_MODE" \
EMBED_PROVIDER="$EMBED_PROVIDER" \
INGEST_TARGETS="$INGEST_TARGETS" \
RAW_NODE_SYNC="$RAW_NODE_SYNC" \
RUN_KDC_SEED="$RUN_KDC_SEED" \
"$ROOT_DIR/scripts/bootstrap_sample_dev.sh"

if [[ ",${INGEST_TARGETS// /}," == *",mysql,"* ]]; then
  nlk_count="$(docker compose -f "$COMPOSE_FILE" exec -T mysql mysql -ubsl -pbsl -D bsl -Nse "SELECT COUNT(*) FROM nlk_raw_nodes;")"
  raw_count="$(docker compose -f "$COMPOSE_FILE" exec -T mysql mysql -ubsl -pbsl -D bsl -Nse "SELECT COUNT(*) FROM raw_node;")"
  echo "nlk_raw_nodes rows: ${nlk_count:-0}"
  echo "raw_node rows: ${raw_count:-0}"
fi

echo "Sample reset bootstrap complete."
