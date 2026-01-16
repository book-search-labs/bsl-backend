CREATE TABLE audit_log (
  audit_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  actor_admin_id BIGINT UNSIGNED NOT NULL,
  action VARCHAR(64) NOT NULL,
  resource_type VARCHAR(64) NOT NULL,
  resource_id VARCHAR(128),
  before_json JSON NULL,
  after_json JSON NULL,
  request_id VARCHAR(64),
  trace_id VARCHAR(64),
  ip VARCHAR(64),
  user_agent VARCHAR(255),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_audit_actor_time (actor_admin_id, created_at),
  INDEX idx_audit_action_time (action, created_at),
  CONSTRAINT fk_audit_admin FOREIGN KEY(actor_admin_id) REFERENCES admin_account(admin_id)
) ENGINE=InnoDB;

CREATE TABLE ops_task (
  task_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  task_type VARCHAR(32) NOT NULL,     -- MODERATION/REINDEX/IMPORT/QUALITY_FIX...
  status VARCHAR(16) NOT NULL,        -- OPEN/IN_PROGRESS/DONE/FAILED
  payload_json JSON NOT NULL,
  assigned_admin_id BIGINT UNSIGNED,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_ops_status_time (status, created_at),
  CONSTRAINT fk_ops_admin FOREIGN KEY(assigned_admin_id) REFERENCES admin_account(admin_id)
) ENGINE=InnoDB;

CREATE TABLE job_run (
  job_run_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  job_type VARCHAR(32) NOT NULL,      -- REINDEX/INGEST/EXPORT...
  status VARCHAR(16) NOT NULL,        -- RUNNING/SUCCESS/FAILED
  params_json JSON,
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME,
  error_message TEXT,
  INDEX idx_job_status_time (status, started_at)
) ENGINE=InnoDB;

-- v1.1 FIX: dedup_key NOT NULL so UNIQUE really enforces idempotency
CREATE TABLE outbox_event (
  event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  event_type VARCHAR(64) NOT NULL,
  aggregate_type VARCHAR(64) NOT NULL,
  aggregate_id VARCHAR(128) NOT NULL,
  dedup_key CHAR(64) NOT NULL,
  payload_json JSON NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'NEW',  -- NEW/SENT/FAILED
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  sent_at DATETIME,
  INDEX idx_outbox_status_time (status, created_at),
  UNIQUE KEY uk_outbox_dedup (dedup_key)
) ENGINE=InnoDB;
