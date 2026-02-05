CREATE TABLE admin_action_approval (
  approval_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  requested_by_admin_id BIGINT UNSIGNED NOT NULL,
  action VARCHAR(128) NOT NULL,
  resource VARCHAR(128) NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
  reason VARCHAR(255) NULL,
  approved_by_admin_id BIGINT UNSIGNED NULL,
  requested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  approved_at DATETIME NULL,
  expires_at DATETIME NULL,
  request_id VARCHAR(64),
  trace_id VARCHAR(64),
  INDEX idx_approval_status_time (status, requested_at),
  INDEX idx_approval_admin_time (requested_by_admin_id, requested_at)
) ENGINE=InnoDB;
