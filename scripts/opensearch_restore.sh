#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 SNAPSHOT_NAME" >&2
  exit 1
fi

SNAPSHOT_NAME="$1"
OS_URL="${OS_URL:-http://localhost:9200}"
SNAPSHOT_REPO="${SNAPSHOT_REPO:-bsl_snapshots}"

payload='{"indices":"*","ignore_unavailable":true,"include_global_state":false}'

echo "Restoring snapshot '$SNAPSHOT_NAME' from repo '$SNAPSHOT_REPO'..."
curl -fsS -XPOST "$OS_URL/_snapshot/$SNAPSHOT_REPO/$SNAPSHOT_NAME/_restore?wait_for_completion=true" \
  -H 'Content-Type: application/json' \
  -d "$payload"

echo "Restore completed."
