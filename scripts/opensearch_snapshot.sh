#!/usr/bin/env bash
set -euo pipefail

OS_URL="${OS_URL:-http://localhost:9200}"
SNAPSHOT_REPO="${SNAPSHOT_REPO:-bsl_snapshots}"
SNAPSHOT_LOCATION="${SNAPSHOT_LOCATION:-/usr/share/opensearch/backup}"
SNAPSHOT_NAME="${SNAPSHOT_NAME:-bsl_$(date +%Y%m%d_%H%M%S)}"

payload=$(cat <<JSON
{
  "type": "fs",
  "settings": {
    "location": "$SNAPSHOT_LOCATION",
    "compress": true
  }
}
JSON
)

echo "Registering snapshot repo '$SNAPSHOT_REPO'..."
curl -fsS -XPUT "$OS_URL/_snapshot/$SNAPSHOT_REPO" \
  -H 'Content-Type: application/json' \
  -d "$payload" >/dev/null

echo "Creating snapshot '$SNAPSHOT_NAME'..."
curl -fsS -XPUT "$OS_URL/_snapshot/$SNAPSHOT_REPO/$SNAPSHOT_NAME?wait_for_completion=true" \
  -H 'Content-Type: application/json' \
  -d '{"indices":"*","ignore_unavailable":true,"include_global_state":false}'

echo "Snapshot completed: $SNAPSHOT_NAME"
