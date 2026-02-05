#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FAST_MODE="${FAST_MODE:-1}"

FAST_MODE="$FAST_MODE" INGEST_TARGETS="mysql" "$SCRIPT_DIR/run_ingest.sh"
