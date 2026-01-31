CREATE TABLE material_merge_group (
  group_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  status VARCHAR(16) NOT NULL DEFAULT 'OPEN',
  rule_version VARCHAR(32) NOT NULL,
  group_key CHAR(64) NOT NULL,
  master_material_id VARCHAR(64) NULL,
  members_json JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_material_merge_group (rule_version, group_key),
  INDEX idx_material_merge_status (status, updated_at),
  INDEX idx_material_merge_master (master_material_id)
) ENGINE=InnoDB;

CREATE TABLE agent_alias_candidate (
  candidate_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  status VARCHAR(16) NOT NULL DEFAULT 'OPEN',
  rule_version VARCHAR(32) NOT NULL,
  candidate_key CHAR(64) NOT NULL,
  canonical_agent_id VARCHAR(64) NOT NULL,
  variants_json JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_agent_alias_candidate (rule_version, candidate_key),
  INDEX idx_agent_alias_canonical (canonical_agent_id),
  INDEX idx_agent_alias_status (status, updated_at)
) ENGINE=InnoDB;
