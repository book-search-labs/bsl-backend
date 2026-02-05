#!/usr/bin/env bash
set -euo pipefail

DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-bsl}"
DB_PASSWORD="${DB_PASSWORD:-bsl}"
DB_NAME="${DB_NAME:-bsl}"

RETENTION_DAYS="${AUDIT_LOG_RETENTION_DAYS:-90}"

echo "Purging audit_log entries older than ${RETENTION_DAYS} days..."
MYSQL_PWD="$DB_PASSWORD" mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" "$DB_NAME" \
  -e "DELETE FROM audit_log WHERE created_at < NOW() - INTERVAL ${RETENTION_DAYS} DAY;"

echo "Done."
