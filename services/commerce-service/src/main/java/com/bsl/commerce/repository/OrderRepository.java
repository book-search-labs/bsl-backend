package com.bsl.commerce.repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.sql.Timestamp;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {
    private final JdbcTemplate jdbcTemplate;

    public OrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Map<String, Object> findOrderById(long orderId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT order_id, order_no, user_id, cart_id, status, total_amount, currency, shipping_fee, discount_amount, "
                + "payment_method, idempotency_key, shipping_snapshot_json, created_at, updated_at "
                + "FROM orders WHERE order_id = ?",
            orderId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Map<String, Object> findOrderByIdempotencyKey(String idempotencyKey) {
        if (idempotencyKey == null) {
            return null;
        }
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT order_id, order_no, user_id, cart_id, status, total_amount, currency, shipping_fee, discount_amount, "
                + "payment_method, idempotency_key, shipping_snapshot_json, created_at, updated_at "
                + "FROM orders WHERE idempotency_key = ?",
            idempotencyKey
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<Map<String, Object>> listOrdersByUser(long userId, int limit) {
        return jdbcTemplate.queryForList(
            "SELECT order_id, order_no, user_id, cart_id, status, total_amount, currency, shipping_fee, discount_amount, "
                + "payment_method, idempotency_key, shipping_snapshot_json, created_at, updated_at "
                + "FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            userId,
            limit
        );
    }

    public long insertOrder(
        long userId,
        Long cartId,
        String status,
        int totalAmount,
        String currency,
        int shippingFee,
        int discountAmount,
        String paymentMethod,
        String idempotencyKey,
        String shippingSnapshotJson,
        String orderNo
    ) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO orders (order_no, user_id, cart_id, status, total_amount, currency, shipping_fee, "
                    + "discount_amount, payment_method, idempotency_key, shipping_snapshot_json) "
                    + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setString(1, orderNo);
            ps.setLong(2, userId);
            if (cartId == null) {
                ps.setObject(3, null);
            } else {
                ps.setLong(3, cartId);
            }
            ps.setString(4, status);
            ps.setInt(5, totalAmount);
            ps.setString(6, currency);
            ps.setInt(7, shippingFee);
            ps.setInt(8, discountAmount);
            ps.setString(9, paymentMethod);
            ps.setString(10, idempotencyKey);
            ps.setString(11, shippingSnapshotJson);
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        return key == null ? 0L : key.longValue();
    }

    public void insertOrderItems(List<OrderItemInsert> items) {
        jdbcTemplate.batchUpdate(
            "INSERT INTO order_item (order_id, sku_id, seller_id, offer_id, qty, unit_price, item_amount, status, "
                + "captured_at, price_snapshot_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            items,
            items.size(),
            (ps, item) -> {
                ps.setLong(1, item.orderId());
                ps.setLong(2, item.skuId());
                ps.setLong(3, item.sellerId());
                if (item.offerId() == null) {
                    ps.setObject(4, null);
                } else {
                    ps.setLong(4, item.offerId());
                }
                ps.setInt(5, item.qty());
                ps.setInt(6, item.unitPrice());
                ps.setInt(7, item.itemAmount());
                ps.setString(8, item.status());
                if (item.capturedAt() == null) {
                    ps.setObject(9, null);
                } else {
                    ps.setTimestamp(9, Timestamp.from(item.capturedAt()));
                }
                ps.setString(10, item.priceSnapshotJson());
            }
        );
    }

    public List<Map<String, Object>> findOrderItems(long orderId) {
        return jdbcTemplate.queryForList(
            "SELECT order_item_id, order_id, sku_id, seller_id, offer_id, qty, unit_price, item_amount, status, "
                + "captured_at, price_snapshot_json, created_at FROM order_item WHERE order_id = ? ORDER BY order_item_id",
            orderId
        );
    }

    public void insertOrderEvent(
        long orderId,
        String eventType,
        String fromStatus,
        String toStatus,
        String reasonCode,
        String payloadJson
    ) {
        jdbcTemplate.update(
            "INSERT INTO order_event (order_id, event_type, from_status, to_status, reason_code, payload_json) "
                + "VALUES (?, ?, ?, ?, ?, ?)",
            orderId,
            eventType,
            fromStatus,
            toStatus,
            reasonCode,
            payloadJson
        );
    }

    public List<Map<String, Object>> findOrderEvents(long orderId) {
        return jdbcTemplate.queryForList(
            "SELECT order_event_id, order_id, event_type, from_status, to_status, reason_code, payload_json, created_at "
                + "FROM order_event WHERE order_id = ? ORDER BY order_event_id",
            orderId
        );
    }

    public void updateOrderStatus(long orderId, String status) {
        jdbcTemplate.update(
            "UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE order_id = ?",
            status,
            orderId
        );
    }

    public void updateOrderTotals(long orderId, int totalAmount, int shippingFee, int discountAmount) {
        jdbcTemplate.update(
            "UPDATE orders SET total_amount = ?, shipping_fee = ?, discount_amount = ?, updated_at = CURRENT_TIMESTAMP "
                + "WHERE order_id = ?",
            totalAmount,
            shippingFee,
            discountAmount,
            orderId
        );
    }

    public record OrderItemInsert(
        long orderId,
        long skuId,
        long sellerId,
        Long offerId,
        int qty,
        int unitPrice,
        int itemAmount,
        String status,
        java.time.Instant capturedAt,
        String priceSnapshotJson
    ) {
    }
}
