ALTER TABLE settlement_line
  ADD COLUMN refund_amount INT NOT NULL DEFAULT 0 AFTER total_fees;
