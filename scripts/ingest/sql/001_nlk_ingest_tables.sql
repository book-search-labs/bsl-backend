CREATE DATABASE IF NOT EXISTS bsl;
USE bsl;

CREATE TABLE IF NOT EXISTS nlk_raw_nodes (
  raw_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  record_id VARCHAR(255) NOT NULL,
  record_types JSON NULL,
  dataset VARCHAR(64) NOT NULL,
  source_file VARCHAR(255) NOT NULL,
  updated_at DATETIME NULL,
  updated_at_raw VARCHAR(64) NULL,
  raw_json JSON NOT NULL,
  raw_hash CHAR(64) NOT NULL,
  ingested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_nlk_raw (record_id, dataset, source_file),
  INDEX idx_nlk_raw_record (record_id),
  INDEX idx_nlk_raw_dataset (dataset)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS nlk_biblio_docs (
  record_id VARCHAR(255) PRIMARY KEY,
  dataset VARCHAR(64) NOT NULL,
  source_file VARCHAR(255) NOT NULL,
  title TEXT NULL,
  title_en TEXT NULL,
  authors JSON NULL,
  authors_text TEXT NULL,
  publisher_name TEXT NULL,
  issued_year SMALLINT NULL,
  language_code TEXT NULL,
  volume BIGINT NULL,
  edition_labels JSON NULL,
  identifiers JSON NULL,
  updated_at DATETIME NULL,
  updated_at_raw VARCHAR(64) NULL,
  raw_json JSON NULL,
  ingested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_nlk_biblio_dataset (dataset),
  INDEX idx_nlk_biblio_year (issued_year),
  FULLTEXT INDEX ft_nlk_biblio_title (title)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
