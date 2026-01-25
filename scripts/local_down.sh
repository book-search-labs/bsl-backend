#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infra/docker/docker-compose.yml"

KEEP_VOLUME="${KEEP_VOLUME:-0}"

if [ "$KEEP_VOLUME" = "1" ]; then
  echo "Stopping OpenSearch + MySQL (keeping volume)..."
  docker compose -f "$COMPOSE_FILE" down
else
  echo "Stopping OpenSearch + MySQL (removing volume)..."
  docker compose -f "$COMPOSE_FILE" down -v
fi
