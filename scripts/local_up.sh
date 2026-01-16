#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infra/docker/docker-compose.yml"
OS_URL="${OS_URL:-http://localhost:9200}"

print_logs() {
  echo "OpenSearch logs (last 200 lines):"
  docker compose -f "$COMPOSE_FILE" logs opensearch --tail=200 || true
}

trap 'print_logs' ERR

echo "Starting OpenSearch (docker compose)..."
docker compose -f "$COMPOSE_FILE" up -d

echo "Waiting for OpenSearch to become ready..."
for i in $(seq 1 60); do
  if curl -fsS "$OS_URL/_cluster/health?wait_for_status=yellow&timeout=1s" >/dev/null 2>&1; then
    echo "OpenSearch is ready."
    break
  fi

  if [ "$i" -eq 60 ]; then
    echo "OpenSearch did not become ready in time (60s). Is port 9200 available?" >&2
    exit 1
  fi
  sleep 1
done

echo "Bootstrapping indices + aliases..."
"$SCRIPT_DIR/os_bootstrap_indices_v1_1.sh"

echo "Seeding doc/vec indices..."
"$SCRIPT_DIR/os_seed_books_v1_1.sh"

echo "Done."
