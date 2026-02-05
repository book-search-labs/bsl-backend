CREATE TABLE ingest_batch
(
  batch_id        BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  source_name     VARCHAR(64) NOT NULL,
  source_type     VARCHAR(32) NOT NULL,                   -- nlk_jsonld/material/agent/concept/...
  file_name       VARCHAR(255),
  file_size_bytes BIGINT,
  sha256          CHAR(64),
  status          VARCHAR(16) NOT NULL DEFAULT 'RUNNING', -- RUNNING/SUCCESS/FAILED
  started_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at     DATETIME,
  error_message   TEXT,
  INDEX           idx_batch_status (status, started_at)
) ENGINE=InnoDB;

CREATE TABLE raw_node
(
  raw_id             BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  batch_id           BIGINT UNSIGNED NOT NULL,

  node_id            VARCHAR(255) NOT NULL, -- @id (CURIE)
  node_hash          BINARY(32)
    GENERATED ALWAYS AS (UNHEX(SHA2(node_id, 256))) STORED,

  node_types         JSON NULL,             -- @type (string/array)
  entity_kind        VARCHAR(32)  NOT NULL, -- MATERIAL/AGENT/CONCEPT/LIBRARY/...

  payload            JSON         NOT NULL, -- node JSON
  payload_uri        VARCHAR(1024) NULL,
  payload_size_bytes BIGINT NULL,
  payload_hash       CHAR(64)     NOT NULL,

  ingested_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

  UNIQUE KEY uk_raw_batch_node (batch_id, node_id),
  UNIQUE KEY uk_raw_batch_hash (batch_id, node_hash),

  INDEX              idx_raw_node_id (node_id),
  INDEX              idx_raw_node_hash (node_hash),
  INDEX              idx_raw_kind_time (entity_kind, ingested_at)
) ENGINE=InnoDB;
