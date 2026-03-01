ALTER TABLE webhook_event
  ADD COLUMN retry_count INT NOT NULL DEFAULT 0 AFTER error_message,
  ADD COLUMN last_retry_at DATETIME NULL AFTER retry_count,
  ADD COLUMN next_retry_at DATETIME NULL AFTER last_retry_at,
  ADD INDEX idx_webhook_retry_queue (process_status, signature_ok, next_retry_at, retry_count);
