ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS payment_expires_at DATETIME NULL AFTER idempotency_key,
  ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 0 AFTER payment_expires_at;

CREATE INDEX idx_orders_status_expires ON orders (status, payment_expires_at);

CREATE TABLE IF NOT EXISTS order_status_history (
  history_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  order_id BIGINT UNSIGNED NOT NULL,
  from_status VARCHAR(32) NULL,
  to_status VARCHAR(32) NOT NULL,
  reason VARCHAR(255) NULL,
  actor_type VARCHAR(40) NOT NULL,
  actor_id VARCHAR(100) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_order_status_history_order (order_id, created_at),
  INDEX idx_order_status_history_created (created_at)
) ENGINE=InnoDB;
