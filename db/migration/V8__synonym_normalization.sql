CREATE TABLE synonym_set (
  synonym_set_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(64) NOT NULL,             -- e.g. "books_synonyms_ko"
  version VARCHAR(32) NOT NULL,
  status VARCHAR(16) NOT NULL,           -- DRAFT/ACTIVE/ARCHIVED
  rules_json JSON NOT NULL,              -- rules (can be row-splitted later)
  created_by_admin_id BIGINT UNSIGNED,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_syn (name, version),
  INDEX idx_syn_active (name, status)
) ENGINE=InnoDB;
