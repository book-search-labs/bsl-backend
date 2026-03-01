-- Backfill: active refund requests should move order status to REFUND_PENDING.
-- Affected historical rows were created before refund request -> order status transition was implemented.

INSERT INTO order_event (order_id, event_type, from_status, to_status, reason_code, payload_json)
SELECT
  o.order_id,
  'REFUND_REQUESTED',
  o.status,
  'REFUND_PENDING',
  'BACKFILL',
  JSON_OBJECT('source', 'V30__refund_pending_backfill')
FROM orders o
JOIN (
  SELECT DISTINCT order_id
  FROM refund
  WHERE status IN ('REQUESTED', 'APPROVED', 'PROCESSING')
) active_refund ON active_refund.order_id = o.order_id
WHERE o.status IN ('PAID', 'READY_TO_SHIP', 'SHIPPED', 'DELIVERED', 'PARTIALLY_REFUNDED')
  AND NOT EXISTS (
    SELECT 1
    FROM order_event oe
    WHERE oe.order_id = o.order_id
      AND oe.to_status = 'REFUND_PENDING'
  );

UPDATE orders o
JOIN (
  SELECT DISTINCT order_id
  FROM refund
  WHERE status IN ('REQUESTED', 'APPROVED', 'PROCESSING')
) active_refund ON active_refund.order_id = o.order_id
SET o.status = 'REFUND_PENDING',
    o.updated_at = CURRENT_TIMESTAMP
WHERE o.status IN ('PAID', 'READY_TO_SHIP', 'SHIPPED', 'DELIVERED', 'PARTIALLY_REFUNDED');
