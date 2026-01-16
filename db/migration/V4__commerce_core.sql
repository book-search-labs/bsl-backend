CREATE TABLE seller (
  seller_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE/SUSPENDED
  policy_json JSON,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE sku (
  sku_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  material_id VARCHAR(128) NOT NULL,
  sku_code VARCHAR(64) UNIQUE,
  format VARCHAR(32),               -- HARDCOVER/PAPERBACK/EBOOK/SET...
  edition VARCHAR(64),
  pack_size INT DEFAULT 1,
  status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  attrs_json JSON,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_sku_material (material_id),
  CONSTRAINT fk_sku_material FOREIGN KEY(material_id) REFERENCES material(material_id)
) ENGINE=InnoDB;

CREATE TABLE offer (
  offer_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  sku_id BIGINT UNSIGNED NOT NULL,
  seller_id BIGINT UNSIGNED NOT NULL,
  currency CHAR(3) NOT NULL DEFAULT 'KRW',
  list_price INT NOT NULL,
  sale_price INT NOT NULL,
  start_at DATETIME,
  end_at DATETIME,
  status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  shipping_policy_json JSON,
  purchase_limit_json JSON,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_offer_sku (sku_id),
  INDEX idx_offer_seller (seller_id),
  INDEX idx_offer_active (status, start_at, end_at),
  CONSTRAINT fk_offer_sku FOREIGN KEY(sku_id) REFERENCES sku(sku_id),
  CONSTRAINT fk_offer_seller FOREIGN KEY(seller_id) REFERENCES seller(seller_id)
) ENGINE=InnoDB;

CREATE TABLE current_offer (
  sku_id BIGINT UNSIGNED PRIMARY KEY,
  offer_id BIGINT UNSIGNED NOT NULL,
  computed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reason VARCHAR(64) NOT NULL DEFAULT 'AUTO',
  CONSTRAINT fk_co_sku FOREIGN KEY(sku_id) REFERENCES sku(sku_id),
  CONSTRAINT fk_co_offer FOREIGN KEY(offer_id) REFERENCES offer(offer_id)
) ENGINE=InnoDB;

-- v1.1 FIX: available is generated to avoid inconsistency
CREATE TABLE inventory_balance (
  sku_id BIGINT UNSIGNED NOT NULL,
  seller_id BIGINT UNSIGNED NOT NULL,
  on_hand INT NOT NULL DEFAULT 0,
  reserved INT NOT NULL DEFAULT 0,
  available INT AS (on_hand - reserved) STORED,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY(sku_id, seller_id),
  CONSTRAINT fk_ib_sku FOREIGN KEY(sku_id) REFERENCES sku(sku_id),
  CONSTRAINT fk_ib_seller FOREIGN KEY(seller_id) REFERENCES seller(seller_id)
) ENGINE=InnoDB;

CREATE TABLE inventory_ledger (
  ledger_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  sku_id BIGINT UNSIGNED NOT NULL,
  seller_id BIGINT UNSIGNED NOT NULL,
  type VARCHAR(32) NOT NULL,          -- ADJUST/RESERVE/RELEASE/DEDUCT/RESTOCK
  delta INT NOT NULL,
  ref_type VARCHAR(32),               -- ORDER/REFUND/JOB/ADMIN
  ref_id VARCHAR(128),
  note VARCHAR(255),
  created_by_admin_id BIGINT UNSIGNED,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_ledger_sku_time (sku_id, created_at),
  INDEX idx_ledger_ref (ref_type, ref_id),
  CONSTRAINT fk_il_sku FOREIGN KEY(sku_id) REFERENCES sku(sku_id),
  CONSTRAINT fk_il_seller FOREIGN KEY(seller_id) REFERENCES seller(seller_id),
  CONSTRAINT fk_il_admin FOREIGN KEY(created_by_admin_id) REFERENCES admin_account(admin_id)
) ENGINE=InnoDB;

CREATE TABLE user_address (
  address_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(64) NOT NULL,
  phone VARCHAR(32) NOT NULL,
  zip VARCHAR(16),
  addr1 VARCHAR(255),
  addr2 VARCHAR(255),
  is_default TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_addr_user (user_id, is_default),
  CONSTRAINT fk_addr_user FOREIGN KEY(user_id) REFERENCES user_account(user_id)
) ENGINE=InnoDB;

CREATE TABLE cart (
  cart_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_cart_user (user_id),
  CONSTRAINT fk_cart_user FOREIGN KEY(user_id) REFERENCES user_account(user_id)
) ENGINE=InnoDB;

CREATE TABLE cart_item (
  cart_item_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  cart_id BIGINT UNSIGNED NOT NULL,
  sku_id BIGINT UNSIGNED NOT NULL,
  seller_id BIGINT UNSIGNED NOT NULL,
  qty INT NOT NULL,
  added_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_cart_line (cart_id, sku_id, seller_id),
  INDEX idx_ci_cart (cart_id),
  CONSTRAINT fk_ci_cart FOREIGN KEY(cart_id) REFERENCES cart(cart_id),
  CONSTRAINT fk_ci_sku FOREIGN KEY(sku_id) REFERENCES sku(sku_id),
  CONSTRAINT fk_ci_seller FOREIGN KEY(seller_id) REFERENCES seller(seller_id)
) ENGINE=InnoDB;

CREATE TABLE orders (
  order_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  order_no VARCHAR(32) UNIQUE,
  user_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(24) NOT NULL,     -- CREATED/PAID/READY/SHIPPED/DELIVERED/CANCELED/REFUNDING/REFUNDED
  total_amount INT NOT NULL DEFAULT 0,
  currency CHAR(3) NOT NULL DEFAULT 'KRW',
  shipping_snapshot_json JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_orders_user_time (user_id, created_at),
  INDEX idx_orders_status_time (status, created_at),
  CONSTRAINT fk_orders_user FOREIGN KEY(user_id) REFERENCES user_account(user_id)
) ENGINE=InnoDB;

CREATE TABLE order_item (
  order_item_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  order_id BIGINT UNSIGNED NOT NULL,
  sku_id BIGINT UNSIGNED NOT NULL,
  seller_id BIGINT UNSIGNED NOT NULL,
  offer_id BIGINT UNSIGNED,
  qty INT NOT NULL,
  unit_price INT NOT NULL,
  item_amount INT NOT NULL,
  status VARCHAR(24) NOT NULL DEFAULT 'ORDERED',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_oi_order (order_id),
  CONSTRAINT fk_oi_order FOREIGN KEY(order_id) REFERENCES orders(order_id),
  CONSTRAINT fk_oi_sku FOREIGN KEY(sku_id) REFERENCES sku(sku_id),
  CONSTRAINT fk_oi_seller FOREIGN KEY(seller_id) REFERENCES seller(seller_id),
  CONSTRAINT fk_oi_offer FOREIGN KEY(offer_id) REFERENCES offer(offer_id)
) ENGINE=InnoDB;

CREATE TABLE order_event (
  order_event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  order_id BIGINT UNSIGNED NOT NULL,
  from_status VARCHAR(24),
  to_status VARCHAR(24) NOT NULL,
  reason_code VARCHAR(32),
  payload_json JSON,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_oe_order_time (order_id, created_at),
  CONSTRAINT fk_oe_order FOREIGN KEY(order_id) REFERENCES orders(order_id)
) ENGINE=InnoDB;

CREATE TABLE payment (
  payment_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  order_id BIGINT UNSIGNED NOT NULL,
  method VARCHAR(16) NOT NULL,        -- CARD/TRANSFER/...
  status VARCHAR(16) NOT NULL,        -- READY/APPROVED/FAILED/CANCELED
  amount INT NOT NULL,
  pg_tx_id VARCHAR(128),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_payment_pg (pg_tx_id),
  INDEX idx_payment_order (order_id),
  CONSTRAINT fk_payment_order FOREIGN KEY(order_id) REFERENCES orders(order_id)
) ENGINE=InnoDB;

CREATE TABLE refund (
  refund_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  order_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(16) NOT NULL,          -- REQUESTED/APPROVED/REJECTED/COMPLETED
  reason_code VARCHAR(32),
  amount INT NOT NULL,
  approved_by_admin_id BIGINT UNSIGNED,
  requested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_refund_status_time (status, requested_at),
  CONSTRAINT fk_refund_order FOREIGN KEY(order_id) REFERENCES orders(order_id),
  CONSTRAINT fk_refund_admin FOREIGN KEY(approved_by_admin_id) REFERENCES admin_account(admin_id)
) ENGINE=InnoDB;

CREATE TABLE refund_item (
  refund_id BIGINT UNSIGNED NOT NULL,
  order_item_id BIGINT UNSIGNED NOT NULL,
  qty INT NOT NULL,
  amount INT NOT NULL,
  PRIMARY KEY(refund_id, order_item_id),
  CONSTRAINT fk_ri_refund FOREIGN KEY(refund_id) REFERENCES refund(refund_id),
  CONSTRAINT fk_ri_order_item FOREIGN KEY(order_item_id) REFERENCES order_item(order_item_id)
) ENGINE=InnoDB;

CREATE TABLE shipment (
  shipment_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  order_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(16) NOT NULL,          -- READY/SHIPPED/DELIVERED/CANCELED
  carrier VARCHAR(32),
  tracking_no VARCHAR(64),
  shipped_at DATETIME,
  delivered_at DATETIME,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_ship_order (order_id),
  CONSTRAINT fk_ship_order FOREIGN KEY(order_id) REFERENCES orders(order_id)
) ENGINE=InnoDB;

CREATE TABLE shipment_item (
  shipment_id BIGINT UNSIGNED NOT NULL,
  order_item_id BIGINT UNSIGNED NOT NULL,
  qty INT NOT NULL,
  PRIMARY KEY(shipment_id, order_item_id),
  CONSTRAINT fk_si_ship FOREIGN KEY(shipment_id) REFERENCES shipment(shipment_id),
  CONSTRAINT fk_si_order_item FOREIGN KEY(order_item_id) REFERENCES order_item(order_item_id)
) ENGINE=InnoDB;

CREATE TABLE shipment_event (
  shipment_event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  shipment_id BIGINT UNSIGNED NOT NULL,
  event_type VARCHAR(32) NOT NULL,
  event_time DATETIME NOT NULL,
  payload_json JSON,
  INDEX idx_se_ship_time (shipment_id, event_time),
  CONSTRAINT fk_se_ship FOREIGN KEY(shipment_id) REFERENCES shipment(shipment_id)
) ENGINE=InnoDB;
