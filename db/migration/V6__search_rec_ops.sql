CREATE TABLE policy (
  policy_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  policy_type VARCHAR(24) NOT NULL,   -- SEARCH/RANKING/RECOMMENDATION
  version VARCHAR(32) NOT NULL,
  status VARCHAR(16) NOT NULL,        -- DRAFT/ACTIVE/ARCHIVED
  config_json JSON NOT NULL,
  created_by_admin_id BIGINT UNSIGNED,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_policy_type_ver (policy_type, version),
  INDEX idx_policy_active (policy_type, status)
) ENGINE=InnoDB;

CREATE TABLE feature_flag (
  flag_key VARCHAR(64) PRIMARY KEY,
  enabled TINYINT(1) NOT NULL DEFAULT 0,
  rule_json JSON,
  updated_by_admin_id BIGINT UNSIGNED,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE experiment (
  experiment_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  status VARCHAR(16) NOT NULL,       -- DRAFT/RUNNING/STOPPED
  traffic_json JSON NOT NULL,        -- bucket/ratio
  variants_json JSON NOT NULL,       -- policy/param bindings
  start_at DATETIME,
  end_at DATETIME,
  created_by_admin_id BIGINT UNSIGNED,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_exp_status_time (status, start_at)
) ENGINE=InnoDB;

CREATE TABLE model_registry (
  model_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  model_type VARCHAR(24) NOT NULL,      -- EMBEDDING/RERANKER/LTR/LLM
  name VARCHAR(255) NOT NULL,
  version VARCHAR(64) NOT NULL,
  artifact_uri VARCHAR(1024),
  config_json JSON,
  status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_model (model_type, name, version)
) ENGINE=InnoDB;

CREATE TABLE eval_run (
  eval_run_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  eval_type VARCHAR(24) NOT NULL,       -- OFFLINE/ONLINE
  model_id BIGINT UNSIGNED,
  dataset VARCHAR(255),
  metrics_json JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_eval_time (created_at)
) ENGINE=InnoDB;
