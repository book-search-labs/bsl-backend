CREATE TABLE normalization_rule_set (
  normalization_rule_set_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(64) NOT NULL,
  version VARCHAR(32) NOT NULL,
  status VARCHAR(16) NOT NULL,           -- DRAFT/ACTIVE/ARCHIVED
  rules_json JSON NOT NULL,
  created_by_admin_id BIGINT UNSIGNED,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_normalization (name, version),
  INDEX idx_normalization_active (name, status)
) ENGINE=InnoDB;
