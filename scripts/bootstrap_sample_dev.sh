#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/compose.yaml"

FLYWAY_IMAGE="${FLYWAY_IMAGE:-flyway/flyway:10}"
DB_USER="${DB_USER:-bsl}"
DB_PASSWORD="${DB_PASSWORD:-bsl}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
INGEST_INSTALL_DEPS="${INGEST_INSTALL_DEPS:-1}"
FAST_MODE="${FAST_MODE:-1}"
EMBED_PROVIDER="${EMBED_PROVIDER:-toy}"
INGEST_TARGETS="${INGEST_TARGETS:-mysql,opensearch}"
RAW_NODE_SYNC="${RAW_NODE_SYNC:-1}"
RUN_KDC_SEED="${RUN_KDC_SEED:-1}"

create_external_volumes() {
  docker volume create docker_mysql-data >/dev/null
  docker volume create docker_opensearch-data >/dev/null
}

wait_service_ready() {
  local service="$1"
  local timeout_sec="${2:-180}"
  local elapsed=0
  local cid=""

  while [ "$elapsed" -lt "$timeout_sec" ]; do
    cid="$(docker compose -f "$COMPOSE_FILE" ps -q "$service" || true)"
    if [ -n "$cid" ]; then
      break
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  if [ -z "$cid" ]; then
    echo "Unable to resolve container id for service: $service" >&2
    exit 1
  fi

  elapsed=0
  while [ "$elapsed" -lt "$timeout_sec" ]; do
    local status
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid")"
    if [ "$status" = "healthy" ] || [ "$status" = "running" ]; then
      echo "$service is ready ($status)."
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done

  echo "Service $service did not become ready within ${timeout_sec}s." >&2
  docker compose -f "$COMPOSE_FILE" logs "$service" --tail=200 || true
  exit 1
}

resolve_compose_network() {
  local cid
  cid="$(docker compose -f "$COMPOSE_FILE" ps -q mysql)"
  docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$cid" | head -n1
}

run_flyway() {
  local network_name="$1"
  shift
  docker run --rm \
    --network "$network_name" \
    -v "$ROOT_DIR/db/migration:/flyway/sql:ro" \
    "$FLYWAY_IMAGE" \
    -connectRetries=60 \
    "-url=jdbc:mysql://mysql:3306/bsl?allowPublicKeyRetrieval=true&useSSL=false" \
    "-user=$DB_USER" \
    "-password=$DB_PASSWORD" \
    "$@"
}

contains_mysql_target() {
  local targets=",${INGEST_TARGETS// /},"
  case "$targets" in
    *,mysql,*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

mysql_count() {
  local table_name="$1"
  docker compose -f "$COMPOSE_FILE" exec -T mysql \
    mysql -u"$DB_USER" -p"$DB_PASSWORD" -D bsl -Nse "SELECT COUNT(*) FROM ${table_name}"
}

run_kdc_seed_load() {
  if [ "$RUN_KDC_SEED" != "1" ]; then
    return 0
  fi
  echo "Running KDC seed load..."
  mysql --local-infile=1 --protocol=tcp \
    -h "$DB_HOST" -P "$DB_PORT" \
    -u"$DB_USER" -p"$DB_PASSWORD" \
    bsl < "$ROOT_DIR/db/seeds/kdc_seed_load.sql"
}

echo "Step 1/4: docker compose up (mysql, opensearch, dashboards)"
create_external_volumes
docker compose -f "$COMPOSE_FILE" up -d mysql opensearch opensearch-dashboards
wait_service_ready mysql 180
wait_service_ready opensearch 180

NETWORK_NAME="$(resolve_compose_network)"
if [ -z "$NETWORK_NAME" ]; then
  echo "Failed to resolve docker compose network name." >&2
  exit 1
fi

echo "Step 2/4: Flyway migrate to V2 only"
run_flyway "$NETWORK_NAME" -target=2 migrate

echo "Step 3/4: sample ingest"
RESET=1 \
FAST_MODE="$FAST_MODE" \
INSTALL_DEPS="$INGEST_INSTALL_DEPS" \
NLK_INPUT_MODE=sample \
EMBED_PROVIDER="$EMBED_PROVIDER" \
INGEST_TARGETS="$INGEST_TARGETS" \
RAW_NODE_SYNC="$RAW_NODE_SYNC" \
"$ROOT_DIR/scripts/ingest/run_ingest.sh"

if contains_mysql_target && [ "$RAW_NODE_SYNC" = "1" ]; then
  RAW_NODE_COUNT="$(mysql_count raw_node)"
  if [ -z "$RAW_NODE_COUNT" ] || [ "$RAW_NODE_COUNT" -eq 0 ]; then
    echo "raw_node is empty after sample ingest. Check ingest logs." >&2
    exit 1
  fi
  echo "raw_node rows after ingest: $RAW_NODE_COUNT"
fi

echo "Step 4/4: Flyway migrate from V3 to latest"
run_flyway "$NETWORK_NAME" migrate

run_kdc_seed_load

echo "Done: sample development bootstrap complete."
