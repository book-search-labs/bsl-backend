-- MySQL retention tables (full logs should go to BigQuery)

-- v1.1 FIX: use query_hash in PK instead of long query_text
CREATE TABLE user_recent_query (
  user_id BIGINT UNSIGNED NOT NULL,
  query_hash CHAR(64) NOT NULL,          -- sha256(normalized_query)
  query_text VARCHAR(512) NOT NULL,      -- original
  last_used_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  use_count INT NOT NULL DEFAULT 1,
  PRIMARY KEY(user_id, query_hash),
  INDEX idx_urq_time (user_id, last_used_at)
) ENGINE=InnoDB;

CREATE TABLE user_recent_view (
  user_id BIGINT UNSIGNED NOT NULL,
  material_id VARCHAR(128) NOT NULL,
  last_viewed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  view_count INT NOT NULL DEFAULT 1,
  PRIMARY KEY(user_id, material_id),
  INDEX idx_urv_time (user_id, last_viewed_at)
) ENGINE=InnoDB;

CREATE TABLE user_feedback (
  feedback_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NULL,
  session_id VARCHAR(64) NULL,
  feedback_type VARCHAR(16) NOT NULL,   -- SEARCH/RECO
  target_type VARCHAR(16) NOT NULL,     -- MATERIAL/QUERY
  target_id VARCHAR(128) NOT NULL,      -- material_id or query_id/hash
  `signal` VARCHAR(32) NOT NULL,          -- LIKE/DISLIKE/NOT_INTERESTED/REPORT/...
  note VARCHAR(255) NULL,
  context_json JSON NULL,               -- request_id, position, experiment, etc
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_fb_user_time (user_id, created_at),
  INDEX idx_fb_target_time (target_type, target_id, created_at)
) ENGINE=InnoDB;
