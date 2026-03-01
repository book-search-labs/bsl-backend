-- Async payment lifecycle fields (checkout session + webhook-driven confirmation)
ALTER TABLE payment
  ADD COLUMN checkout_session_id VARCHAR(128) NULL AFTER provider_payment_id,
  ADD COLUMN return_url VARCHAR(512) NULL AFTER checkout_session_id,
  ADD COLUMN webhook_url VARCHAR(512) NULL AFTER return_url,
  ADD COLUMN checkout_url VARCHAR(1024) NULL AFTER webhook_url,
  ADD COLUMN expires_at DATETIME NULL AFTER checkout_url,
  ADD COLUMN authorized_at DATETIME NULL AFTER expires_at,
  ADD COLUMN captured_at DATETIME NULL AFTER authorized_at,
  ADD COLUMN failed_at DATETIME NULL AFTER captured_at,
  ADD COLUMN canceled_at DATETIME NULL AFTER failed_at,
  ADD INDEX idx_payment_checkout_session (checkout_session_id),
  ADD INDEX idx_payment_status_updated (status, updated_at);

CREATE TABLE webhook_event (
  webhook_event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  provider VARCHAR(32) NOT NULL,
  event_id VARCHAR(128) NOT NULL,
  payment_id BIGINT UNSIGNED NULL,
  signature_ok TINYINT(1) NOT NULL DEFAULT 0,
  received_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  processed_at DATETIME NULL,
  payload_json JSON,
  process_status VARCHAR(16) NOT NULL DEFAULT 'RECEIVED',
  error_message VARCHAR(512) NULL,
  UNIQUE KEY uk_webhook_event_id (event_id),
  INDEX idx_webhook_payment (payment_id, received_at),
  INDEX idx_webhook_provider_status (provider, process_status, received_at)
) ENGINE=InnoDB;
