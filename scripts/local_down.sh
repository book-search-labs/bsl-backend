#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="infra/docker/docker-compose.yml"

KEEP_VOLUME="${KEEP_VOLUME:-0}"

if [ "$KEEP_VOLUME" = "1" ]; then
  echo "Stopping OpenSearch (keeping volume)..."
  docker compose -f "$COMPOSE_FILE" down
else
  echo "Stopping OpenSearch (removing volume)..."
  docker compose -f "$COMPOSE_FILE" down -v
fi
