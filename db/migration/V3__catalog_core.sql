CREATE TABLE material (
  material_id VARCHAR(128) PRIMARY KEY,  -- @id
  kind VARCHAR(24) NOT NULL,             -- OFFLINE/ONLINE/THESIS/SERIAL/...
  title TEXT,
  subtitle TEXT,
  description LONGTEXT,
  toc LONGTEXT,
  language_code VARCHAR(16),
  publisher_name VARCHAR(255),
  issued_year SMALLINT,
  published_at DATETIME,
  cover_url VARCHAR(1024),
  extras_json JSON,
  last_raw_id BIGINT UNSIGNED,
  last_payload_hash CHAR(64),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_material_kind (kind),
  INDEX idx_material_year (issued_year),
  INDEX idx_material_lang (language_code),
  INDEX idx_material_publisher (publisher_name),
  FULLTEXT INDEX ft_material_text (title, subtitle, description, toc)
) ENGINE=InnoDB;

CREATE TABLE material_override (
  material_id VARCHAR(128) PRIMARY KEY,
  title TEXT NULL,
  subtitle TEXT NULL,
  description LONGTEXT NULL,
  publisher_name VARCHAR(255) NULL,
  issued_year SMALLINT NULL,
  language_code VARCHAR(16) NULL,
  cover_url VARCHAR(1024) NULL,
  hidden TINYINT(1) NULL,              -- search 제외
  override_json JSON NULL,
  updated_by_admin_id BIGINT UNSIGNED,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_mo_material FOREIGN KEY(material_id) REFERENCES material(material_id),
  CONSTRAINT fk_mo_admin FOREIGN KEY(updated_by_admin_id) REFERENCES admin_account(admin_id)
) ENGINE=InnoDB;

CREATE TABLE material_merge (
  from_material_id VARCHAR(128) PRIMARY KEY,
  to_material_id VARCHAR(128) NOT NULL,
  reason VARCHAR(255),
  created_by_admin_id BIGINT UNSIGNED,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_merge_to (to_material_id),
  CONSTRAINT fk_mm_from FOREIGN KEY(from_material_id) REFERENCES material(material_id),
  CONSTRAINT fk_mm_to FOREIGN KEY(to_material_id) REFERENCES material(material_id),
  CONSTRAINT fk_mm_admin FOREIGN KEY(created_by_admin_id) REFERENCES admin_account(admin_id)
) ENGINE=InnoDB;

CREATE TABLE material_identifier (
  material_id VARCHAR(128) NOT NULL,
  scheme VARCHAR(24) NOT NULL,     -- ISBN/ISSN/DOI...
  value VARCHAR(255) NOT NULL,
  normalized VARCHAR(255),
  PRIMARY KEY(material_id, scheme, value),
  INDEX idx_ident_lookup (scheme, value),
  CONSTRAINT fk_mid_material FOREIGN KEY(material_id) REFERENCES material(material_id)
) ENGINE=InnoDB;

CREATE TABLE agent (
  agent_id VARCHAR(128) PRIMARY KEY,
  agent_type VARCHAR(16) NOT NULL,  -- PERSON/ORG
  preferred_name VARCHAR(255),
  extras_json JSON,
  INDEX idx_agent_name (preferred_name)
) ENGINE=InnoDB;

-- v1.1 FIX: no nullable columns in PK. Use surrogate key + unique(material_id, role, ord).
CREATE TABLE material_agent (
  material_agent_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  material_id VARCHAR(128) NOT NULL,
  role VARCHAR(32) NOT NULL,          -- AUTHOR/EDITOR/TRANSLATOR/...
  ord INT NOT NULL,                   -- display order (0..n)
  agent_id VARCHAR(128) NULL,
  agent_name_raw VARCHAR(255) NULL,
  UNIQUE KEY uk_ma (material_id, role, ord),
  INDEX idx_ma_agent (agent_id),
  CONSTRAINT fk_ma_material FOREIGN KEY(material_id) REFERENCES material(material_id),
  CONSTRAINT fk_ma_agent FOREIGN KEY(agent_id) REFERENCES agent(agent_id)
) ENGINE=InnoDB;

CREATE TABLE concept (
  concept_id VARCHAR(128) PRIMARY KEY,
  pref_label VARCHAR(255),
  scheme VARCHAR(128),
  extras_json JSON,
  INDEX idx_concept_label (pref_label)
) ENGINE=InnoDB;

CREATE TABLE material_concept (
  material_id VARCHAR(128) NOT NULL,
  concept_id VARCHAR(128) NOT NULL,
  rel_type VARCHAR(16) NOT NULL DEFAULT 'SUBJECT',
  PRIMARY KEY(material_id, concept_id, rel_type),
  INDEX idx_mc_concept (concept_id),
  CONSTRAINT fk_mc_material FOREIGN KEY(material_id) REFERENCES material(material_id),
  CONSTRAINT fk_mc_concept FOREIGN KEY(concept_id) REFERENCES concept(concept_id)
) ENGINE=InnoDB;
