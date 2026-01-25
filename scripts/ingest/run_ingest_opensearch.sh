#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

INGEST_TARGETS="opensearch" "$SCRIPT_DIR/run_ingest.sh"
