CREATE TABLE support_ticket (
  ticket_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  ticket_no VARCHAR(32) NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  order_id BIGINT UNSIGNED NULL,
  category VARCHAR(32) NOT NULL DEFAULT 'GENERAL',
  severity VARCHAR(16) NOT NULL DEFAULT 'MEDIUM',
  status VARCHAR(24) NOT NULL DEFAULT 'RECEIVED',
  summary VARCHAR(255) NOT NULL,
  detail_json JSON NULL,
  error_code VARCHAR(64) NULL,
  chat_session_id VARCHAR(64) NULL,
  chat_request_id VARCHAR(64) NULL,
  expected_response_at DATETIME NULL,
  resolved_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_support_ticket_no (ticket_no),
  INDEX idx_support_ticket_user_time (user_id, created_at),
  INDEX idx_support_ticket_status_time (status, created_at),
  INDEX idx_support_ticket_order (order_id)
) ENGINE=InnoDB;

CREATE TABLE support_ticket_event (
  ticket_event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  ticket_id BIGINT UNSIGNED NOT NULL,
  event_type VARCHAR(32) NOT NULL,
  from_status VARCHAR(24) NULL,
  to_status VARCHAR(24) NULL,
  note VARCHAR(255) NULL,
  payload_json JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_support_ticket_event_ticket (ticket_id, created_at)
) ENGINE=InnoDB;
