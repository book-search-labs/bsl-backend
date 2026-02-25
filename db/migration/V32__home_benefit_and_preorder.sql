ALTER TABLE cart_content_item
  ADD COLUMN IF NOT EXISTS benefit_code VARCHAR(64) NULL AFTER content_type,
  ADD COLUMN IF NOT EXISTS badge VARCHAR(64) NULL AFTER description,
  ADD COLUMN IF NOT EXISTS discount_type VARCHAR(24) NULL AFTER badge,
  ADD COLUMN IF NOT EXISTS discount_value INT NULL AFTER discount_type,
  ADD COLUMN IF NOT EXISTS min_order_amount INT NULL AFTER discount_value,
  ADD COLUMN IF NOT EXISTS max_discount_amount INT NULL AFTER min_order_amount,
  ADD COLUMN IF NOT EXISTS valid_from DATETIME NULL AFTER max_discount_amount,
  ADD COLUMN IF NOT EXISTS valid_to DATETIME NULL AFTER valid_from,
  ADD COLUMN IF NOT EXISTS daily_limit INT NULL AFTER valid_to,
  ADD COLUMN IF NOT EXISTS remaining_daily INT NULL AFTER daily_limit,
  ADD COLUMN IF NOT EXISTS link_url VARCHAR(500) NULL AFTER remaining_daily,
  ADD COLUMN IF NOT EXISTS cta_label VARCHAR(64) NULL AFTER link_url;

UPDATE cart_content_item
SET
  benefit_code = CASE sort_order
    WHEN 10 THEN 'CARD_LOTTE_04'
    WHEN 20 THEN 'PAY_KAKAOPAY_4000'
    WHEN 30 THEN 'PAY_TOSS_2000'
    WHEN 40 THEN 'CARD_NH_2500'
    WHEN 50 THEN 'PAY_PAYCO_POINT_1P'
    ELSE benefit_code
  END,
  badge = CASE sort_order
    WHEN 10 THEN '카드'
    WHEN 20 THEN '간편결제'
    WHEN 30 THEN '간편결제'
    WHEN 40 THEN '카드'
    WHEN 50 THEN '포인트'
    ELSE badge
  END,
  discount_type = CASE sort_order
    WHEN 10 THEN 'PERCENT'
    WHEN 20 THEN 'FIXED'
    WHEN 30 THEN 'FIXED'
    WHEN 40 THEN 'FIXED'
    WHEN 50 THEN 'PERCENT'
    ELSE discount_type
  END,
  discount_value = CASE sort_order
    WHEN 10 THEN 4
    WHEN 20 THEN 4000
    WHEN 30 THEN 2000
    WHEN 40 THEN 2500
    WHEN 50 THEN 1
    ELSE discount_value
  END,
  min_order_amount = CASE sort_order
    WHEN 10 THEN 10000
    WHEN 20 THEN 25000
    WHEN 30 THEN 20000
    WHEN 40 THEN 30000
    WHEN 50 THEN 10000
    ELSE min_order_amount
  END,
  max_discount_amount = CASE sort_order
    WHEN 10 THEN 10000
    WHEN 50 THEN 5000
    ELSE max_discount_amount
  END,
  valid_from = DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 1 DAY),
  valid_to = CASE sort_order
    WHEN 20 THEN DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 1 DAY)
    WHEN 30 THEN DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 1 DAY)
    ELSE DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 7 DAY)
  END,
  daily_limit = CASE sort_order
    WHEN 20 THEN 500
    WHEN 30 THEN 350
    ELSE NULL
  END,
  remaining_daily = CASE sort_order
    WHEN 20 THEN 183
    WHEN 30 THEN 129
    ELSE NULL
  END,
  link_url = '/benefits',
  cta_label = '혜택 받기'
WHERE content_type = 'PROMOTION';

CREATE TABLE IF NOT EXISTS preorder_item (
  preorder_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  material_id VARCHAR(128) NOT NULL,
  seller_id BIGINT UNSIGNED NOT NULL,
  sku_id BIGINT UNSIGNED NULL,
  title_override VARCHAR(255) NULL,
  subtitle VARCHAR(255) NULL,
  summary VARCHAR(500) NULL,
  preorder_price INT NOT NULL,
  list_price INT NULL,
  discount_rate INT NULL,
  preorder_start_at DATETIME NOT NULL,
  preorder_end_at DATETIME NOT NULL,
  release_at DATETIME NOT NULL,
  reservation_limit INT NULL,
  badge VARCHAR(64) NULL,
  cta_label VARCHAR(64) NOT NULL DEFAULT '예약구매',
  sort_order INT NOT NULL DEFAULT 100,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_preorder_active_window (is_active, preorder_start_at, preorder_end_at, sort_order),
  INDEX idx_preorder_release (release_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS preorder_reservation (
  reservation_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  preorder_id BIGINT UNSIGNED NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  qty INT NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'RESERVED',
  reserved_price INT NOT NULL,
  order_id BIGINT UNSIGNED NULL,
  note VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_preorder_reservation_user (preorder_id, user_id),
  INDEX idx_preorder_reservation_status (preorder_id, status, created_at),
  INDEX idx_preorder_reservation_user (user_id, status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO seller (name, status, policy_json)
SELECT 'BSL Store', 'ACTIVE', JSON_OBJECT('auto_provisioned', TRUE)
WHERE NOT EXISTS (SELECT 1 FROM seller);

SET @preorder_seller_id := (SELECT seller_id FROM seller ORDER BY seller_id ASC LIMIT 1);
SET @preorder_seq := 0;

INSERT INTO preorder_item (
  material_id,
  seller_id,
  sku_id,
  title_override,
  subtitle,
  summary,
  preorder_price,
  list_price,
  discount_rate,
  preorder_start_at,
  preorder_end_at,
  release_at,
  reservation_limit,
  badge,
  cta_label,
  sort_order
)
SELECT
  seeded.material_id,
  @preorder_seller_id,
  seeded.sku_id,
  seeded.display_title,
  CONCAT('출간 예정 · ', DATE_FORMAT(DATE_ADD(CURRENT_DATE, INTERVAL seeded.seq + 6 DAY), '%m월 %d일')),
  CONCAT('예약구매 고객 전용 혜택과 함께 먼저 만나보세요.'),
  ROUND(COALESCE(seeded.sale_price, 15000 + (seeded.seq * 900)), -2),
  ROUND(COALESCE(seeded.list_price, seeded.sale_price, 18000 + (seeded.seq * 900)), -2),
  CASE
    WHEN COALESCE(seeded.list_price, 0) > 0 AND COALESCE(seeded.sale_price, 0) > 0
      THEN LEAST(40, GREATEST(5, ROUND((seeded.list_price - seeded.sale_price) * 100 / seeded.list_price)))
    ELSE 10
  END,
  DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 1 DAY),
  DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 14 DAY),
  DATE_ADD(CURRENT_TIMESTAMP, INTERVAL (seeded.seq + 6) DAY),
  300,
  CASE MOD(seeded.seq, 3)
    WHEN 1 THEN '사전예약 한정'
    WHEN 2 THEN '초판 혜택'
    ELSE '출간 예정'
  END,
  '예약구매',
  seeded.seq * 10
FROM (
  SELECT
    src.material_id,
    src.sku_id,
    src.sale_price,
    src.list_price,
    src.display_title,
    (@preorder_seq := @preorder_seq + 1) AS seq
  FROM (
    SELECT
      m.material_id,
      s.sku_id,
      o.sale_price,
      o.list_price,
      COALESCE(NULLIF(TRIM(m.title), ''), NULLIF(TRIM(m.label), ''), CONCAT('출간 예정 도서 ', m.material_id)) AS display_title,
      m.date_published,
      m.updated_at
    FROM material m
    LEFT JOIN sku s
      ON s.material_id = m.material_id
      AND (s.seller_id = @preorder_seller_id OR s.seller_id IS NULL)
    LEFT JOIN current_offer co ON co.sku_id = s.sku_id
    LEFT JOIN offer o ON o.offer_id = co.offer_id
    WHERE COALESCE(NULLIF(TRIM(m.title), ''), NULLIF(TRIM(m.label), '')) IS NOT NULL
    ORDER BY COALESCE(m.date_published, DATE('2099-12-31')) DESC, m.updated_at DESC, m.material_id ASC
    LIMIT 8
  ) src
) seeded
WHERE NOT EXISTS (
  SELECT 1 FROM preorder_item p WHERE p.material_id = seeded.material_id
);
