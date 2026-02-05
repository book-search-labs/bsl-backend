ALTER TABLE reindex_job
  MODIFY COLUMN status VARCHAR(32) NOT NULL,
  MODIFY COLUMN to_physical VARCHAR(128) NULL,
  MODIFY COLUMN started_at DATETIME NULL,
  ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  ADD COLUMN progress_json JSON NULL,
  ADD COLUMN error_json JSON NULL,
  ADD COLUMN paused_at DATETIME NULL;

CREATE INDEX idx_reindex_status_time ON reindex_job (status, updated_at);

CREATE TABLE reindex_error (
  reindex_error_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  reindex_job_id BIGINT UNSIGNED NOT NULL,
  doc_id VARCHAR(128) NOT NULL,
  status_code INT NULL,
  reason TEXT NULL,
  payload_json JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_reindex_error_job (reindex_job_id, created_at)
) ENGINE=InnoDB;
