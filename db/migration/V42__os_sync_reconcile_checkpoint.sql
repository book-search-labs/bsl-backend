-- B-0304: checkpoint storage for MySQL <-> OpenSearch reconciler

CREATE TABLE IF NOT EXISTS reconcile_checkpoint (
  checkpoint_name VARCHAR(64) NOT NULL PRIMARY KEY,
  last_updated_at DATETIME NULL,
  last_material_id VARCHAR(64) NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE INDEX idx_outbox_material_status_occurred
  ON outbox_event (event_type, status, occurred_at);
