#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/compose.yaml"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-bsl-observability}"

echo "Stopping observability stack..."
docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" --profile observability down
