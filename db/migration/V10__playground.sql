CREATE TABLE playground_snapshot (
  snapshot_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(255),
  query_text VARCHAR(512) NOT NULL,
  pipeline_json JSON NOT NULL,       -- toggles/weights/model versions
  request_json JSON NOT NULL,
  response_json JSON NOT NULL,       -- results + debug summary
  created_by_admin_id BIGINT UNSIGNED,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_pg_time (created_at),
  CONSTRAINT fk_pg_admin FOREIGN KEY(created_by_admin_id) REFERENCES admin_account(admin_id)
) ENGINE=InnoDB;

CREATE TABLE playground_judgement (
  judgement_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  snapshot_id BIGINT UNSIGNED NOT NULL,
  material_id VARCHAR(128) NOT NULL,
  label VARCHAR(16) NOT NULL,        -- GOOD/BAD/IRRELEVANT...
  note VARCHAR(255),
  created_by_admin_id BIGINT UNSIGNED,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_pj_snap (snapshot_id),
  CONSTRAINT fk_pj_snap FOREIGN KEY(snapshot_id) REFERENCES playground_snapshot(snapshot_id),
  CONSTRAINT fk_pj_material FOREIGN KEY(material_id) REFERENCES material(material_id),
  CONSTRAINT fk_pj_admin FOREIGN KEY(created_by_admin_id) REFERENCES admin_account(admin_id)
) ENGINE=InnoDB;
