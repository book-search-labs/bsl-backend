CREATE TABLE ingest_batch (
  batch_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  source_name VARCHAR(64) NOT NULL,
  source_type VARCHAR(32) NOT NULL,  -- nlk_jsonld/material/agent/concept/...
  file_name VARCHAR(255),
  file_size_bytes BIGINT,
  sha256 CHAR(64),
  status VARCHAR(16) NOT NULL DEFAULT 'RUNNING', -- RUNNING/SUCCESS/FAILED
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME,
  error_message TEXT,
  INDEX idx_batch_status (status, started_at)
) ENGINE=InnoDB;

CREATE TABLE raw_node (
  raw_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  batch_id BIGINT UNSIGNED NOT NULL,
  node_id VARCHAR(128) NOT NULL,         -- @id
  node_types JSON,
  entity_kind VARCHAR(32) NOT NULL,      -- MATERIAL/AGENT/CONCEPT/LIBRARY...
  payload JSON NULL,                      -- optional
  payload_uri VARCHAR(1024) NULL,         -- object storage pointer recommended
  payload_size_bytes BIGINT NULL,
  payload_hash CHAR(64) NOT NULL,
  ingested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_raw_batch_node (batch_id, node_id),
  INDEX idx_raw_node_id (node_id),
  INDEX idx_raw_kind_time (entity_kind, ingested_at),
  CONSTRAINT fk_raw_batch FOREIGN KEY (batch_id) REFERENCES ingest_batch(batch_id)
) ENGINE=InnoDB;
