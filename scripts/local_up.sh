#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="infra/docker/docker-compose.yml"
OS_URL="${OS_URL:-http://localhost:9200}"

echo "Starting OpenSearch (docker compose)..."
docker compose -f "$COMPOSE_FILE" up -d

echo "Waiting for OpenSearch to become ready..."
for i in $(seq 1 60); do
  if curl -fsS "$OS_URL/_cluster/health?wait_for_status=yellow&timeout=1s" >/dev/null 2>&1; then
    echo "OpenSearch is ready."
    break
  fi

  if [ "$i" -eq 60 ]; then
    echo "OpenSearch did not become ready in time (60s). Printing logs:"
    docker compose -f "$COMPOSE_FILE" logs opensearch --tail=200
    exit 1
  fi
  sleep 1
done

echo "Seeding OpenSearch index..."
scripts/os_seed_books_v1.sh

echo "Done."
