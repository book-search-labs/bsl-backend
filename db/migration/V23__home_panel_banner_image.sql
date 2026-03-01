ALTER TABLE home_panel_item
  ADD COLUMN banner_image_url VARCHAR(1000) NULL AFTER cta_label;

UPDATE home_panel_item
SET banner_image_url = CASE
  WHEN panel_type = 'NOTICE'
    THEN CONCAT('https://picsum.photos/seed/bsl-notice-', LPAD(panel_item_id, 4, '0'), '/1200/420')
  ELSE CONCAT('https://picsum.photos/seed/bsl-event-', LPAD(panel_item_id, 4, '0'), '/1200/420')
END
WHERE banner_image_url IS NULL;
