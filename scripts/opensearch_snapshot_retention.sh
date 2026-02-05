#!/usr/bin/env bash
set -euo pipefail

OS_URL="${OS_URL:-http://localhost:9200}"
SNAPSHOT_REPO="${SNAPSHOT_REPO:-bsl_snapshots}"
RETENTION_DAYS="${SNAPSHOT_RETENTION_DAYS:-7}"
export SNAPSHOT_RETENTION_DAYS="$RETENTION_DAYS"

if ! command -v python >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
  echo "python is required for retention cleanup" >&2
  exit 1
fi
PYTHON_BIN=$(command -v python || command -v python3)

json=$(curl -fsS "$OS_URL/_snapshot/$SNAPSHOT_REPO/_all")

if [ -z "${SNAPSHOT_NAMES:-}" ]; then
  SNAPSHOT_NAMES=$(echo "$json" | $PYTHON_BIN - <<'PY'
import json
import os
import sys
import time

payload = json.load(sys.stdin)
retention_days = int(os.environ.get("SNAPSHOT_RETENTION_DAYS", "7"))
cutoff = time.time() - retention_days * 86400

stale = []
for snap in payload.get("snapshots", []):
    end_time = snap.get("end_time_in_millis")
    name = snap.get("snapshot")
    if end_time and name and end_time / 1000 < cutoff:
        stale.append(name)

print(" ".join(stale))
PY
)
fi

if [ -z "$SNAPSHOT_NAMES" ]; then
  echo "No snapshots older than ${RETENTION_DAYS} days."
  exit 0
fi

echo "Deleting snapshots: $SNAPSHOT_NAMES"
for snap in $SNAPSHOT_NAMES; do
  curl -fsS -XDELETE "$OS_URL/_snapshot/$SNAPSHOT_REPO/$snap" >/dev/null
  echo "Deleted $snap"
done
