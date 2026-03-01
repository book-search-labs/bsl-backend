CREATE TABLE llm_audit_log (
  llm_audit_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  service_name VARCHAR(32) NOT NULL DEFAULT 'llm-gateway',
  provider VARCHAR(32) NOT NULL,
  model VARCHAR(128) NOT NULL,
  trace_id VARCHAR(64) NOT NULL,
  request_id VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  reason_code VARCHAR(64) NULL,
  tokens INT UNSIGNED NOT NULL DEFAULT 0,
  cost_usd DECIMAL(12, 6) NOT NULL DEFAULT 0,
  event_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  metadata_json JSON NULL,
  INDEX idx_llm_audit_time (event_time),
  INDEX idx_llm_audit_status_time (status, event_time),
  INDEX idx_llm_audit_trace_time (trace_id, event_time),
  INDEX idx_llm_audit_request_time (request_id, event_time)
) ENGINE=InnoDB;
