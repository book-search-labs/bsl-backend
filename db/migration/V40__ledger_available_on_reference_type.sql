ALTER TABLE ledger_entry
  ADD COLUMN available_on DATE NULL AFTER occurred_at,
  ADD COLUMN reference_type VARCHAR(32) NULL AFTER available_on;

UPDATE ledger_entry
SET reference_type = CASE
  WHEN entry_type = 'REFUND' THEN 'REFUND_COMPLETE'
  ELSE 'PAYMENT_CAPTURE'
END
WHERE reference_type IS NULL;

UPDATE ledger_entry
SET available_on = CASE
  WHEN entry_type = 'REFUND' THEN DATE(occurred_at)
  ELSE DATE_ADD(DATE(occurred_at), INTERVAL 2 DAY)
END
WHERE available_on IS NULL;

ALTER TABLE ledger_entry
  MODIFY COLUMN available_on DATE NOT NULL,
  MODIFY COLUMN reference_type VARCHAR(32) NOT NULL,
  DROP INDEX uk_ledger_reference,
  ADD UNIQUE KEY uk_ledger_reference_type (reference_type, reference_id, entry_type),
  ADD INDEX idx_ledger_available (available_on, seller_id);
