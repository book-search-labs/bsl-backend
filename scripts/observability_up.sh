#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/compose.yaml"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-bsl-observability}"

echo "Starting observability stack (Grafana, Prometheus, Tempo, OTel Collector, Loki, Metabase)..."
docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" --profile observability up -d

echo "Grafana: http://localhost:3000 (admin / ${GRAFANA_ADMIN_PASSWORD:-admin})"
echo "Prometheus: http://localhost:9090"
echo "Tempo: http://localhost:3200"
echo "Loki: http://localhost:3100"
echo "Metabase: http://localhost:3001"
