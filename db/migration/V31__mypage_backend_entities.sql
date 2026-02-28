CREATE TABLE my_coupon (
  coupon_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(255) NOT NULL,
  discount_label VARCHAR(128) NOT NULL,
  expires_at DATE NOT NULL,
  usable TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_my_coupon_user (user_id, usable, expires_at)
) ENGINE=InnoDB;

CREATE TABLE my_voucher (
  voucher_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(255) NOT NULL,
  value INT NOT NULL,
  expires_at DATE NOT NULL,
  used TINYINT(1) NOT NULL DEFAULT 0,
  used_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_my_voucher_user (user_id, used, expires_at)
) ENGINE=InnoDB;

CREATE TABLE my_notification (
  notification_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  category VARCHAR(32) NOT NULL,
  title VARCHAR(255) NOT NULL,
  body VARCHAR(1000) NOT NULL,
  is_read TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  read_at DATETIME NULL,
  INDEX idx_my_notification_user_time (user_id, created_at),
  INDEX idx_my_notification_user_read (user_id, is_read)
) ENGINE=InnoDB;

CREATE TABLE my_notification_preference (
  user_id BIGINT UNSIGNED NOT NULL,
  category VARCHAR(32) NOT NULL,
  label VARCHAR(64) NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, category)
) ENGINE=InnoDB;

CREATE TABLE my_ebook_library (
  entry_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  material_id VARCHAR(128) NOT NULL,
  title VARCHAR(255) NOT NULL,
  author VARCHAR(255) NULL,
  publisher VARCHAR(255) NULL,
  downloaded_at DATETIME NOT NULL,
  drm_policy VARCHAR(255) NOT NULL,
  cover_url VARCHAR(1024) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_my_ebook_user_time (user_id, downloaded_at)
) ENGINE=InnoDB;

CREATE TABLE my_gift (
  gift_id VARCHAR(64) PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  title VARCHAR(255) NOT NULL,
  status VARCHAR(64) NOT NULL,
  direction VARCHAR(16) NOT NULL,
  partner_name VARCHAR(128) NOT NULL,
  message VARCHAR(1000) NOT NULL,
  gift_code VARCHAR(64) NULL,
  expires_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_my_gift_user_time (user_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE my_gift_item (
  gift_item_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  gift_id VARCHAR(64) NOT NULL,
  material_id VARCHAR(128) NOT NULL,
  title VARCHAR(255) NOT NULL,
  author VARCHAR(255) NULL,
  publisher VARCHAR(255) NULL,
  quantity INT NOT NULL,
  unit_price INT NOT NULL,
  cover_url VARCHAR(1024) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_my_gift_item_gift (gift_id, gift_item_id)
) ENGINE=InnoDB;

CREATE TABLE my_comment (
  comment_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  order_id BIGINT UNSIGNED NOT NULL,
  title VARCHAR(255) NOT NULL,
  rating TINYINT UNSIGNED NOT NULL,
  content TEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_my_comment_user_order (user_id, order_id),
  INDEX idx_my_comment_user_time (user_id, created_at)
) ENGINE=InnoDB;

INSERT INTO my_coupon (user_id, name, discount_label, expires_at, usable)
VALUES
  (1, '장바구니 즉시할인', '1,000원 할인', '2026-03-05', 1),
  (1, '신학기 추천도서 쿠폰', '10% 할인', '2026-03-20', 1),
  (1, '지난달 프로모션', '5,000원 할인', '2026-01-30', 0);

INSERT INTO my_voucher (user_id, name, value, expires_at, used, used_at)
VALUES
  (1, '신규 가입 교환권', 1000, '2026-03-31', 0, NULL),
  (1, '봄 맞이 도서 교환권', 3000, '2026-04-10', 0, NULL),
  (1, '만료 교환권', 500, '2026-02-01', 1, '2026-01-25 10:00:00');

INSERT INTO my_notification_preference (user_id, category, label, enabled)
VALUES
  (1, 'order', '주문/배송 알림', 1),
  (1, 'event', '이벤트 알림', 1),
  (1, 'benefit', '혜택 알림', 1),
  (1, 'system', '서비스 알림', 1);

INSERT INTO my_notification (user_id, category, title, body, is_read, created_at, read_at)
VALUES
  (1, 'order', '주문한 상품이 출고 준비 중입니다.', '주문번호 ORD-240211 상품이 곧 출고됩니다.', 0, '2026-02-24 11:10:00', NULL),
  (1, 'event', '신규 이벤트가 시작되었습니다.', '이벤트/공지 페이지에서 이번 주 혜택을 확인해보세요.', 0, '2026-02-23 09:00:00', NULL),
  (1, 'benefit', '포인트가 적립되었습니다.', '1,200P가 적립되었습니다.', 1, '2026-02-22 14:00:00', '2026-02-22 14:05:00'),
  (1, 'system', '알림 설정이 업데이트되었습니다.', '수신 설정 변경 내역이 반영되었습니다.', 1, '2026-02-21 19:40:00', '2026-02-21 19:45:00');

INSERT INTO my_ebook_library (user_id, material_id, title, author, publisher, downloaded_at, drm_policy, cover_url)
VALUES
  (1, 'nlk:CDM200900003', '초등영어교육의 영미문화지도에 관한 연구', '한은경', '釜山外國語大學校', '2026-02-20 09:20:00', '등록 기기 5대, 오프라인 30일', NULL),
  (1, 'nlk:CM000000201', '周易辭典', '장선문', '上海古籍出版社', '2026-02-17 19:10:00', '스트리밍 전용, 다운로드 2회', NULL);

INSERT INTO my_gift (gift_id, user_id, title, status, direction, partner_name, message, gift_code, expires_at, created_at)
VALUES
  ('gift-1', 1, '지인에게 선물한 도서 1건', '전달 완료', 'SENT', '박지윤', '업무에 도움 되길 바랍니다.', NULL, NULL, '2026-02-18 16:10:00'),
  ('gift-2', 1, '받은 선물 1건', '사용 가능', 'RECEIVED', '김민준', '관심 있던 책이라 선물합니다.', 'GIFT-26-0212-441', '2026-03-12 23:59:00', '2026-02-12 09:15:00');

INSERT INTO my_gift_item (gift_id, material_id, title, author, publisher, quantity, unit_price, cover_url)
VALUES
  ('gift-1', 'nlk:CDM200900003', '초등영어교육의 영미문화지도에 관한 연구', '한은경', '釜山外國語大學校', 1, 13300, NULL),
  ('gift-2', 'nlk:CM000000201', '周易辭典', '장선문', '上海古籍出版社', 1, 15400, NULL);

INSERT IGNORE INTO user_saved_material (user_id, material_id, created_at)
VALUES
  (1, 'nlk:CDM200900003', '2026-02-24 10:00:00'),
  (1, 'nlk:CM000000006', '2026-02-23 10:00:00'),
  (1, 'nlk:CM000000201', '2026-02-22 10:00:00');

INSERT INTO loyalty_point_account (user_id, balance)
VALUES (1, 900)
ON DUPLICATE KEY UPDATE balance = balance;

INSERT INTO loyalty_point_ledger (user_id, order_id, type, delta, balance_after, reason, created_at)
VALUES
  (1, NULL, 'EARN', 1200, 1200, '주문 적립', '2026-02-21 10:30:00'),
  (1, NULL, 'ADJUST', 500, 1700, '이벤트 보너스', '2026-02-20 15:00:00'),
  (1, NULL, 'SPEND', -800, 900, '포인트 사용', '2026-02-19 09:30:00');
