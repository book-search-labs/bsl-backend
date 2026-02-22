#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/compose.yaml"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-bsl-backend}"

KEEP_VOLUME="${KEEP_VOLUME:-0}"
MYSQL_VOLUME_NAME="${MYSQL_VOLUME_NAME:-docker_mysql-data}"
OPENSEARCH_VOLUME_NAME="${OPENSEARCH_VOLUME_NAME:-docker_opensearch-data}"
REMOVE_BACKUP_VOLUME="${REMOVE_BACKUP_VOLUME:-1}"
OPENSEARCH_BACKUP_VOLUME="${OPENSEARCH_BACKUP_VOLUME:-${COMPOSE_PROJECT}_opensearch-backup}"

if [ "$KEEP_VOLUME" = "1" ]; then
  echo "Stopping OpenSearch + MySQL (keeping volume)..."
  docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" down
else
  echo "Stopping OpenSearch + MySQL (removing compose-managed volume)..."
  docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" down -v
  echo "Removing external data volumes..."
  docker volume rm -f "$MYSQL_VOLUME_NAME" >/dev/null 2>&1 || true
  docker volume rm -f "$OPENSEARCH_VOLUME_NAME" >/dev/null 2>&1 || true
  if [ "$REMOVE_BACKUP_VOLUME" = "1" ]; then
    docker volume rm -f "$OPENSEARCH_BACKUP_VOLUME" >/dev/null 2>&1 || true
  fi
fi
