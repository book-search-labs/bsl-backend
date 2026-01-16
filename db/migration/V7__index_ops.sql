CREATE TABLE search_index_version (
  index_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  logical_name VARCHAR(64) NOT NULL,      -- books, ac_candidates ...
  physical_name VARCHAR(128) NOT NULL,    -- books_v17_20260115
  schema_hash CHAR(64) NOT NULL,
  status VARCHAR(16) NOT NULL,            -- BUILDING/READY/ACTIVE/DEPRECATED
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_index_phy (physical_name),
  INDEX idx_index_logical (logical_name, status)
) ENGINE=InnoDB;

CREATE TABLE search_index_alias (
  alias_name VARCHAR(64) PRIMARY KEY,     -- books_active
  physical_name VARCHAR(128) NOT NULL,
  switched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE reindex_job (
  reindex_job_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  logical_name VARCHAR(64) NOT NULL,
  from_physical VARCHAR(128),
  to_physical VARCHAR(128) NOT NULL,
  status VARCHAR(16) NOT NULL,            -- RUNNING/SUCCESS/FAILED
  params_json JSON,
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME,
  error_message TEXT
) ENGINE=InnoDB;
