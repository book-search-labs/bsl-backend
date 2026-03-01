-- Ledger + settlement v1
CREATE TABLE ledger_entry (
  ledger_entry_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  seller_id BIGINT UNSIGNED NOT NULL,
  order_id BIGINT UNSIGNED NOT NULL,
  payment_id BIGINT UNSIGNED NULL,
  entry_type VARCHAR(32) NOT NULL,
  amount INT NOT NULL,
  currency CHAR(3) NOT NULL DEFAULT 'KRW',
  occurred_at DATETIME NOT NULL,
  reference_id VARCHAR(128) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_ledger_reference (entry_type, reference_id, seller_id),
  INDEX idx_ledger_settlement (seller_id, occurred_at),
  INDEX idx_ledger_order (order_id, occurred_at)
) ENGINE=InnoDB;

CREATE TABLE settlement_cycle (
  cycle_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'DRAFT',
  generated_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_settlement_cycle_period (start_date, end_date),
  INDEX idx_settlement_cycle_status (status, created_at)
) ENGINE=InnoDB;

CREATE TABLE settlement_line (
  settlement_line_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  cycle_id BIGINT UNSIGNED NOT NULL,
  seller_id BIGINT UNSIGNED NOT NULL,
  gross_sales INT NOT NULL DEFAULT 0,
  total_fees INT NOT NULL DEFAULT 0,
  net_amount INT NOT NULL DEFAULT 0,
  status VARCHAR(16) NOT NULL DEFAULT 'UNPAID',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_settlement_line_cycle_seller (cycle_id, seller_id),
  INDEX idx_settlement_line_cycle (cycle_id, status)
) ENGINE=InnoDB;

CREATE TABLE payout (
  payout_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  settlement_line_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'SCHEDULED',
  paid_at DATETIME NULL,
  failure_reason VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_payout_line (settlement_line_id),
  INDEX idx_payout_status (status, created_at)
) ENGINE=InnoDB;
