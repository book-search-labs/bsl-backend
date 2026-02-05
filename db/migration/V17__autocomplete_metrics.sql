CREATE TABLE ac_suggest_metric (
  suggest_id VARCHAR(128) PRIMARY KEY,
  text VARCHAR(255) NOT NULL,
  type VARCHAR(32) NOT NULL,
  lang VARCHAR(16) NULL,
  impressions_7d DOUBLE NOT NULL DEFAULT 0,
  clicks_7d DOUBLE NOT NULL DEFAULT 0,
  ctr_7d DOUBLE NOT NULL DEFAULT 0,
  popularity_7d DOUBLE NOT NULL DEFAULT 0,
  last_seen_at DATETIME NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_ac_metric_ctr (ctr_7d),
  INDEX idx_ac_metric_pop (popularity_7d),
  INDEX idx_ac_metric_updated (updated_at)
) ENGINE=InnoDB;
