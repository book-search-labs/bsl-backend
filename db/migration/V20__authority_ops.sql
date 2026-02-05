CREATE TABLE agent_alias (
  alias_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  alias_name VARCHAR(255) NOT NULL,
  canonical_name VARCHAR(255) NOT NULL,
  canonical_agent_id VARCHAR(64) NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_agent_alias_name (alias_name),
  INDEX idx_agent_alias_canonical (canonical_agent_id),
  INDEX idx_agent_alias_status (status, updated_at)
) ENGINE=InnoDB;
