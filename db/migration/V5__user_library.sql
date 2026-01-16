CREATE TABLE user_saved_material (
  user_id BIGINT UNSIGNED NOT NULL,
  material_id VARCHAR(128) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, material_id),
  INDEX idx_usm_material (material_id),
  CONSTRAINT fk_usm_user FOREIGN KEY(user_id) REFERENCES user_account(user_id),
  CONSTRAINT fk_usm_material FOREIGN KEY(material_id) REFERENCES material(material_id)
) ENGINE=InnoDB;

CREATE TABLE user_shelf (
  user_id BIGINT UNSIGNED NOT NULL,
  material_id VARCHAR(128) NOT NULL,
  shelf_status VARCHAR(16) NOT NULL, -- WANT/READING/READ
  started_at DATETIME NULL,
  finished_at DATETIME NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, material_id),
  INDEX idx_ushelf_status_time (user_id, shelf_status, updated_at),
  CONSTRAINT fk_ushelf_user FOREIGN KEY(user_id) REFERENCES user_account(user_id),
  CONSTRAINT fk_ushelf_material FOREIGN KEY(material_id) REFERENCES material(material_id)
) ENGINE=InnoDB;

CREATE TABLE user_preference (
  user_id BIGINT UNSIGNED PRIMARY KEY,
  pref_json JSON NOT NULL,
  reco_opt_in TINYINT(1) NOT NULL DEFAULT 1,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_up_user FOREIGN KEY(user_id) REFERENCES user_account(user_id)
) ENGINE=InnoDB;

CREATE TABLE user_consent (
  user_id BIGINT UNSIGNED NOT NULL,
  consent_type VARCHAR(32) NOT NULL, -- TERMS/PRIVACY/MARKETING
  version VARCHAR(32) NOT NULL,
  agreed TINYINT(1) NOT NULL,
  agreed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, consent_type, version),
  CONSTRAINT fk_uc_user FOREIGN KEY(user_id) REFERENCES user_account(user_id)
) ENGINE=InnoDB;
