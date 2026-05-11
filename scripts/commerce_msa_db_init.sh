#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/compose.yaml}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-bsl-backend}"
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-localroot}"
MYSQL_APP_USER="${MYSQL_APP_USER:-bsl}"
MYSQL_APP_PASSWORD="${MYSQL_APP_PASSWORD:-bsl}"
SEED_COMMERCE_MSA_DATA="${SEED_COMMERCE_MSA_DATA:-1}"

mysql_root() {
  docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" exec -T mysql \
    mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$@"
}

apply_sql() {
  local database="$1"
  local file="$2"
  echo "Applying $file -> $database"
  mysql_root "$database" < "$ROOT_DIR/$file"
}

echo "Creating service databases..."
mysql_root <<SQL
CREATE DATABASE IF NOT EXISTS checkout_orchestrator_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS order_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS payment_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS inventory_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS shipment_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS refund_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${MYSQL_APP_USER}'@'%' IDENTIFIED BY '${MYSQL_APP_PASSWORD}';
GRANT ALL PRIVILEGES ON checkout_orchestrator_db.* TO '${MYSQL_APP_USER}'@'%';
GRANT ALL PRIVILEGES ON order_db.* TO '${MYSQL_APP_USER}'@'%';
GRANT ALL PRIVILEGES ON payment_db.* TO '${MYSQL_APP_USER}'@'%';
GRANT ALL PRIVILEGES ON inventory_db.* TO '${MYSQL_APP_USER}'@'%';
GRANT ALL PRIVILEGES ON shipment_db.* TO '${MYSQL_APP_USER}'@'%';
GRANT ALL PRIVILEGES ON refund_db.* TO '${MYSQL_APP_USER}'@'%';
FLUSH PRIVILEGES;
SQL

apply_sql checkout_orchestrator_db db/migration/V43__checkout_orchestrator_saga.sql
apply_sql order_db services/order-service/src/main/resources/db/migration/V1__order_service_schema.sql
apply_sql payment_db services/payment-service/src/main/resources/db/migration/V1__payment_service_schema.sql
apply_sql inventory_db services/inventory-service/src/main/resources/db/migration/V1__inventory_service_schema.sql
apply_sql shipment_db services/shipment-service/src/main/resources/db/migration/V1__shipment_service_schema.sql
apply_sql refund_db services/refund-service/src/main/resources/db/migration/V1__refund_service_schema.sql

if [ "$SEED_COMMERCE_MSA_DATA" = "1" ]; then
  echo "Seeding inventory stock rows..."
  mysql_root inventory_db <<SQL
INSERT INTO book_stock (book_id, available_quantity, reserved_quantity)
VALUES
  ('book-1', 100, 0),
  ('book-2', 100, 0),
  ('book-3', 100, 0)
ON DUPLICATE KEY UPDATE
  available_quantity = GREATEST(available_quantity, VALUES(available_quantity)),
  updated_at = NOW(6);
SQL
else
  echo "Skipping Commerce MSA seed data (SEED_COMMERCE_MSA_DATA=$SEED_COMMERCE_MSA_DATA)."
fi

echo "Commerce MSA databases are ready."
