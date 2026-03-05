-- B-0301: OpenSearch sync outbox contract alignment + consumer idempotency table

ALTER TABLE outbox_event
  ADD COLUMN IF NOT EXISTS occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER payload_json,
  ADD COLUMN IF NOT EXISTS published_at DATETIME NULL AFTER status,
  ADD COLUMN IF NOT EXISTS retry_count INT NOT NULL DEFAULT 0 AFTER published_at,
  ADD COLUMN IF NOT EXISTS last_error TEXT NULL AFTER retry_count;

-- backfill timestamps/state for existing rows
UPDATE outbox_event
SET occurred_at = created_at
WHERE occurred_at IS NULL OR occurred_at = '0000-00-00 00:00:00';

UPDATE outbox_event
SET published_at = COALESCE(published_at, sent_at)
WHERE status = 'SENT' OR sent_at IS NOT NULL;

UPDATE outbox_event
SET status = 'PUBLISHED'
WHERE status = 'SENT';

CREATE INDEX idx_outbox_status_occurred_at ON outbox_event (status, occurred_at);

CREATE TABLE IF NOT EXISTS processed_event (
  event_id BIGINT UNSIGNED NOT NULL,
  handler VARCHAR(128) NOT NULL,
  processed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (event_id, handler),
  INDEX idx_processed_event_processed_at (processed_at)
) ENGINE=InnoDB;
