ALTER TABLE refund
  ADD COLUMN item_amount INT NOT NULL DEFAULT 0 AFTER amount,
  ADD COLUMN shipping_refund_amount INT NOT NULL DEFAULT 0 AFTER item_amount,
  ADD COLUMN return_fee_amount INT NOT NULL DEFAULT 0 AFTER shipping_refund_amount,
  ADD COLUMN policy_code VARCHAR(64) NULL AFTER return_fee_amount;

UPDATE refund
SET item_amount = amount
WHERE item_amount = 0;
