package com.bsl.commerce.repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class RefundRepository {
    private final JdbcTemplate jdbcTemplate;

    public RefundRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Map<String, Object> findRefund(long refundId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT refund_id, order_id, payment_id, status, reason_code, reason_text, provider_refund_id, amount, "
                + "item_amount, shipping_refund_amount, return_fee_amount, policy_code, "
                + "idempotency_key, approved_by_admin_id, requested_at, updated_at FROM refund WHERE refund_id = ?",
            refundId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Map<String, Object> findRefundByIdempotencyKey(String idempotencyKey) {
        if (idempotencyKey == null) {
            return null;
        }
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT refund_id, order_id, payment_id, status, reason_code, reason_text, provider_refund_id, amount, "
                + "item_amount, shipping_refund_amount, return_fee_amount, policy_code, "
                + "idempotency_key, approved_by_admin_id, requested_at, updated_at FROM refund WHERE idempotency_key = ?",
            idempotencyKey
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<Map<String, Object>> listRefundsByOrder(long orderId) {
        return jdbcTemplate.queryForList(
            "SELECT refund_id, order_id, payment_id, status, reason_code, reason_text, provider_refund_id, amount, "
                + "item_amount, shipping_refund_amount, return_fee_amount, policy_code, "
                + "idempotency_key, approved_by_admin_id, requested_at, updated_at FROM refund WHERE order_id = ? "
                + "ORDER BY refund_id DESC",
            orderId
        );
    }

    public List<Map<String, Object>> listRefunds(int limit) {
        return jdbcTemplate.queryForList(
            "SELECT refund_id, order_id, payment_id, status, reason_code, reason_text, provider_refund_id, amount, "
                + "item_amount, shipping_refund_amount, return_fee_amount, policy_code, "
                + "idempotency_key, approved_by_admin_id, requested_at, updated_at FROM refund ORDER BY refund_id DESC LIMIT ?",
            limit
        );
    }

    public long insertRefund(
        long orderId,
        Long paymentId,
        String status,
        String reasonCode,
        String reasonText,
        int itemAmount,
        int shippingRefundAmount,
        int returnFeeAmount,
        int amount,
        String policyCode,
        String idempotencyKey
    ) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO refund (order_id, payment_id, status, reason_code, reason_text, item_amount, "
                    + "shipping_refund_amount, return_fee_amount, amount, policy_code, idempotency_key) "
                    + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setLong(1, orderId);
            if (paymentId == null) {
                ps.setObject(2, null);
            } else {
                ps.setLong(2, paymentId);
            }
            ps.setString(3, status);
            ps.setString(4, reasonCode);
            ps.setString(5, reasonText);
            ps.setInt(6, itemAmount);
            ps.setInt(7, shippingRefundAmount);
            ps.setInt(8, returnFeeAmount);
            ps.setInt(9, amount);
            ps.setString(10, policyCode);
            ps.setString(11, idempotencyKey);
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        return key == null ? 0L : key.longValue();
    }

    public void insertRefundItems(List<RefundItemInsert> items) {
        jdbcTemplate.batchUpdate(
            "INSERT INTO refund_item (refund_id, order_item_id, sku_id, qty, amount) VALUES (?, ?, ?, ?, ?)",
            items,
            items.size(),
            (ps, item) -> {
                ps.setLong(1, item.refundId());
                ps.setLong(2, item.orderItemId());
                if (item.skuId() == null) {
                    ps.setObject(3, null);
                } else {
                    ps.setLong(3, item.skuId());
                }
                ps.setInt(4, item.qty());
                ps.setInt(5, item.amount());
            }
        );
    }

    public List<Map<String, Object>> listRefundItems(long refundId) {
        return jdbcTemplate.queryForList(
            "SELECT refund_id, order_item_id, sku_id, qty, amount FROM refund_item WHERE refund_id = ?",
            refundId
        );
    }

    public void updateRefundStatus(long refundId, String status, Long adminId, String providerRefundId) {
        jdbcTemplate.update(
            "UPDATE refund SET status = ?, approved_by_admin_id = ?, provider_refund_id = ?, updated_at = CURRENT_TIMESTAMP "
                + "WHERE refund_id = ?",
            status,
            adminId,
            providerRefundId,
            refundId
        );
    }

    public void insertRefundEvent(long refundId, String eventType, String payloadJson) {
        jdbcTemplate.update(
            "INSERT INTO refund_event (refund_id, event_type, payload_json) VALUES (?, ?, ?)",
            refundId,
            eventType,
            payloadJson
        );
    }

    public List<Map<String, Object>> listRefundEvents(long refundId) {
        return jdbcTemplate.queryForList(
            "SELECT refund_event_id, refund_id, event_type, payload_json, created_at FROM refund_event "
                + "WHERE refund_id = ? ORDER BY refund_event_id",
            refundId
        );
    }

    public List<Map<String, Object>> sumRefundedQtyByOrder(long orderId) {
        return jdbcTemplate.queryForList(
            "SELECT ri.order_item_id, SUM(ri.qty) AS refunded_qty "
                + "FROM refund_item ri JOIN refund r ON ri.refund_id = r.refund_id "
                + "WHERE r.order_id = ? AND r.status IN ('REQUESTED','APPROVED','PROCESSING','REFUNDED') "
                + "GROUP BY ri.order_item_id",
            orderId
        );
    }

    public Map<String, Object> sumRefundAmountsByOrder(long orderId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT COALESCE(SUM(item_amount), 0) AS item_amount, "
                + "COALESCE(SUM(shipping_refund_amount), 0) AS shipping_refund_amount, "
                + "COALESCE(SUM(return_fee_amount), 0) AS return_fee_amount, "
                + "COALESCE(SUM(amount), 0) AS amount "
                + "FROM refund WHERE order_id = ? "
                + "AND status IN ('REQUESTED','APPROVED','PROCESSING','REFUNDED')",
            orderId
        );
        return rows.isEmpty() ? Map.of() : rows.get(0);
    }

    public record RefundItemInsert(long refundId, long orderItemId, Long skuId, int qty, int amount) {
    }
}
