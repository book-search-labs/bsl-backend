ALTER TABLE home_panel_item
  ADD COLUMN detail_body TEXT NULL AFTER summary;

UPDATE home_panel_item
SET
  starts_at = COALESCE(starts_at, DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 3 DAY)),
  ends_at = COALESCE(ends_at, DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 90 DAY))
WHERE is_active = 1;

UPDATE home_panel_item
SET banner_image_url = CASE
  WHEN panel_type = 'NOTICE' THEN CONCAT(
    '/event-banners/notice-feature-',
    LPAD((((FLOOR(sort_order / 10) - 1) MOD 4) + 1), 2, '0'),
    '.svg'
  )
  ELSE CONCAT(
    '/event-banners/event-feature-',
    LPAD((((FLOOR(sort_order / 10) - 1) MOD 8) + 1), 2, '0'),
    '.svg'
  )
END
WHERE is_active = 1
  AND (
    banner_image_url IS NULL
    OR banner_image_url LIKE 'https://picsum.photos/%'
    OR banner_image_url LIKE '/event-banners/%'
  );

UPDATE home_panel_item
SET detail_body = CONCAT(
  '대상: ', title, '\n',
  '핵심 안내: ', COALESCE(NULLIF(TRIM(subtitle), ''), '상세 안내를 확인해 주세요.'), '\n',
  '요약: ', COALESCE(NULLIF(TRIM(summary), ''), '현재 운영 중인 이벤트/공지입니다.'), '\n',
  '참여/확인 방법: ', CASE
    WHEN panel_type = 'NOTICE' THEN '안내 내용을 확인한 뒤 주문/배송 또는 고객센터 메뉴에서 필요한 작업을 진행해 주세요.'
    ELSE '상단 배너 또는 관련 페이지 이동 버튼을 눌러 해당 기획전 페이지에서 도서를 확인해 주세요.'
  END, '\n',
  '문의: 고객센터 > 1:1 문의'
)
WHERE detail_body IS NULL
   OR TRIM(detail_body) = '';
