CREATE TABLE loyalty_point_account (
  user_id BIGINT UNSIGNED PRIMARY KEY,
  balance INT NOT NULL DEFAULT 0,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE loyalty_point_ledger (
  ledger_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  order_id BIGINT UNSIGNED NULL,
  type VARCHAR(16) NOT NULL,
  delta INT NOT NULL,
  balance_after INT NOT NULL,
  reason VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_lp_order_type (order_id, type),
  INDEX idx_lp_user_time (user_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE cart_content_item (
  item_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  content_type VARCHAR(16) NOT NULL,
  title VARCHAR(255) NOT NULL,
  description VARCHAR(500) NULL,
  sort_order INT NOT NULL DEFAULT 0,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_cart_content_type (content_type, is_active, sort_order)
) ENGINE=InnoDB;

INSERT INTO cart_content_item (content_type, title, description, sort_order, is_active)
VALUES
  ('PROMOTION', '혜택 롯데카드 누구나 0.4% 즉시할인', NULL, 10, 1),
  ('PROMOTION', '혜택 카카오페이 4천원 즉시할인 (일 선착순 500명)', NULL, 20, 1),
  ('PROMOTION', '혜택 토스페이 2천원 즉시할인 (일 선착순 350명)', NULL, 30, 1),
  ('PROMOTION', '혜택 NH카드 2,500원 즉시할인', NULL, 40, 1),
  ('PROMOTION', '혜택 PAYCO 포인트 결제 시 1% 즉시 할인', NULL, 50, 1),
  ('NOTICE', '택배 배송일정은 기본배송지 기준으로 예상일이 노출됩니다.', NULL, 10, 1),
  ('NOTICE', '상품별 배송일정이 다를 시 가장 늦은 일정 기준으로 함께 배송됩니다.', NULL, 20, 1),
  ('NOTICE', '가격/재고는 결제 시점에 최종 반영되며, 변동 시 알림이 표시됩니다.', NULL, 30, 1),
  ('NOTICE', '쿠폰/포인트 적용 시 결제예정금액은 결제 단계에서 다시 계산됩니다.', NULL, 40, 1);
