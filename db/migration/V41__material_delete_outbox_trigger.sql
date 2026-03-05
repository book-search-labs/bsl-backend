-- B-0302: delete/restore producer guard for material lifecycle changes

DROP TRIGGER IF EXISTS trg_material_soft_delete_outbox;
DROP TRIGGER IF EXISTS trg_material_hard_delete_outbox;

DELIMITER $$

CREATE TRIGGER trg_material_soft_delete_outbox
AFTER UPDATE ON material
FOR EACH ROW
BEGIN
  IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
    INSERT IGNORE INTO outbox_event (
      event_type,
      aggregate_type,
      aggregate_id,
      dedup_key,
      payload_json,
      occurred_at,
      status
    ) VALUES (
      'material.delete_requested',
      'material',
      NEW.material_id,
      SHA2(
        CONCAT(
          'material.delete_requested',
          ':',
          NEW.material_id,
          ':',
          DATE_FORMAT(COALESCE(NEW.deleted_at, NOW(6)), '%Y%m%d%H%i%s%f')
        ),
        256
      ),
      JSON_OBJECT('version', 'v1', 'material_id', NEW.material_id),
      NOW(),
      'NEW'
    );
  ELSEIF OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NULL THEN
    INSERT IGNORE INTO outbox_event (
      event_type,
      aggregate_type,
      aggregate_id,
      dedup_key,
      payload_json,
      occurred_at,
      status
    ) VALUES (
      'material.upsert_requested',
      'material',
      NEW.material_id,
      SHA2(
        CONCAT(
          'material.upsert_requested',
          ':',
          NEW.material_id,
          ':',
          DATE_FORMAT(COALESCE(NEW.updated_at, NOW(6)), '%Y%m%d%H%i%s%f')
        ),
        256
      ),
      JSON_OBJECT('version', 'v1', 'material_id', NEW.material_id),
      NOW(),
      'NEW'
    );
  END IF;
END$$

CREATE TRIGGER trg_material_hard_delete_outbox
AFTER DELETE ON material
FOR EACH ROW
BEGIN
  INSERT IGNORE INTO outbox_event (
    event_type,
    aggregate_type,
    aggregate_id,
    dedup_key,
    payload_json,
    occurred_at,
    status
  ) VALUES (
    'material.delete_requested',
    'material',
    OLD.material_id,
    SHA2(
      CONCAT(
        'material.delete_requested',
        ':',
        OLD.material_id,
        ':',
        DATE_FORMAT(NOW(6), '%Y%m%d%H%i%s%f')
      ),
      256
    ),
    JSON_OBJECT('version', 'v1', 'material_id', OLD.material_id),
    NOW(),
    'NEW'
  );
END$$

DELIMITER ;
