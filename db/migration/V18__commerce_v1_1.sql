-- Commerce v1.1 extensions (idempotency, events, snapshots)

ALTER TABLE sku
  ADD COLUMN seller_id BIGINT UNSIGNED NULL AFTER material_id;

ALTER TABLE offer
  ADD COLUMN priority INT NOT NULL DEFAULT 0 AFTER sale_price;

ALTER TABLE inventory_ledger
  ADD COLUMN idempotency_key VARCHAR(128) NULL AFTER delta,
  ADD UNIQUE KEY uk_inventory_ledger_idem (idempotency_key);

ALTER TABLE cart
  ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE' AFTER user_id,
  ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER status;

ALTER TABLE cart_item
  ADD COLUMN offer_id BIGINT UNSIGNED NULL AFTER seller_id,
  ADD COLUMN unit_price INT NULL AFTER offer_id,
  ADD COLUMN currency CHAR(3) NULL AFTER unit_price,
  ADD COLUMN captured_at DATETIME NULL AFTER currency,
  ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER added_at;

ALTER TABLE orders
  ADD COLUMN cart_id BIGINT UNSIGNED NULL AFTER user_id,
  ADD COLUMN idempotency_key VARCHAR(128) NULL AFTER currency,
  ADD COLUMN shipping_fee INT NOT NULL DEFAULT 0 AFTER idempotency_key,
  ADD COLUMN discount_amount INT NOT NULL DEFAULT 0 AFTER shipping_fee,
  ADD COLUMN payment_method VARCHAR(16) NULL AFTER discount_amount,
  ADD UNIQUE KEY uk_orders_idem (idempotency_key);

ALTER TABLE order_item
  ADD COLUMN captured_at DATETIME NULL AFTER item_amount,
  ADD COLUMN price_snapshot_json JSON NULL AFTER captured_at;

ALTER TABLE order_event
  ADD COLUMN event_type VARCHAR(32) NULL AFTER order_id;

ALTER TABLE payment
  ADD COLUMN currency CHAR(3) NOT NULL DEFAULT 'KRW' AFTER amount,
  ADD COLUMN provider VARCHAR(16) NOT NULL DEFAULT 'MOCK' AFTER currency,
  ADD COLUMN provider_payment_id VARCHAR(128) NULL AFTER provider,
  ADD COLUMN idempotency_key VARCHAR(128) NULL AFTER provider_payment_id,
  ADD COLUMN failure_reason VARCHAR(255) NULL AFTER idempotency_key,
  ADD UNIQUE KEY uk_payment_idem (idempotency_key);

CREATE TABLE payment_event (
  payment_event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  payment_id BIGINT UNSIGNED NOT NULL,
  event_type VARCHAR(32) NOT NULL,
  provider_event_id VARCHAR(128),
  payload_json JSON,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_payment_event_provider (provider_event_id),
  INDEX idx_payment_event_payment (payment_id, created_at)
) ENGINE=InnoDB;

ALTER TABLE refund
  ADD COLUMN payment_id BIGINT UNSIGNED NULL AFTER order_id,
  ADD COLUMN idempotency_key VARCHAR(128) NULL AFTER amount,
  ADD COLUMN reason_text VARCHAR(255) NULL AFTER reason_code,
  ADD COLUMN provider_refund_id VARCHAR(128) NULL AFTER reason_text,
  ADD UNIQUE KEY uk_refund_idem (idempotency_key);

ALTER TABLE refund_item
  ADD COLUMN sku_id BIGINT UNSIGNED NULL AFTER order_item_id;

CREATE TABLE refund_event (
  refund_event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  refund_id BIGINT UNSIGNED NOT NULL,
  event_type VARCHAR(32) NOT NULL,
  payload_json JSON,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_refund_event_refund (refund_id, created_at)
) ENGINE=InnoDB;

ALTER TABLE shipment_item
  ADD COLUMN sku_id BIGINT UNSIGNED NULL AFTER order_item_id;
