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
public class ShipmentRepository {
    private final JdbcTemplate jdbcTemplate;

    public ShipmentRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Map<String, Object> findShipment(long shipmentId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT shipment_id, order_id, status, carrier, tracking_no, shipped_at, delivered_at, created_at, updated_at "
                + "FROM shipment WHERE shipment_id = ?",
            shipmentId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<Map<String, Object>> listShipmentsByOrder(long orderId) {
        return jdbcTemplate.queryForList(
            "SELECT shipment_id, order_id, status, carrier, tracking_no, shipped_at, delivered_at, created_at, updated_at "
                + "FROM shipment WHERE order_id = ? ORDER BY shipment_id DESC",
            orderId
        );
    }

    public List<Map<String, Object>> listShipments(int limit) {
        return jdbcTemplate.queryForList(
            "SELECT shipment_id, order_id, status, carrier, tracking_no, shipped_at, delivered_at, created_at, updated_at "
                + "FROM shipment ORDER BY shipment_id DESC LIMIT ?",
            limit
        );
    }

    public long insertShipment(long orderId, String status) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO shipment (order_id, status) VALUES (?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setLong(1, orderId);
            ps.setString(2, status);
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        return key == null ? 0L : key.longValue();
    }

    public void insertShipmentItems(List<ShipmentItemInsert> items) {
        jdbcTemplate.batchUpdate(
            "INSERT INTO shipment_item (shipment_id, order_item_id, sku_id, qty) VALUES (?, ?, ?, ?)",
            items,
            items.size(),
            (ps, item) -> {
                ps.setLong(1, item.shipmentId());
                ps.setLong(2, item.orderItemId());
                if (item.skuId() == null) {
                    ps.setObject(3, null);
                } else {
                    ps.setLong(3, item.skuId());
                }
                ps.setInt(4, item.qty());
            }
        );
    }

    public List<Map<String, Object>> listShipmentItems(long shipmentId) {
        return jdbcTemplate.queryForList(
            "SELECT shipment_id, order_item_id, sku_id, qty FROM shipment_item WHERE shipment_id = ?",
            shipmentId
        );
    }

    public void updateTracking(long shipmentId, String carrier, String trackingNo, String status, Timestamp shippedAt) {
        jdbcTemplate.update(
            "UPDATE shipment SET carrier = ?, tracking_no = ?, status = ?, shipped_at = ?, updated_at = CURRENT_TIMESTAMP "
                + "WHERE shipment_id = ?",
            carrier,
            trackingNo,
            status,
            shippedAt,
            shipmentId
        );
    }

    public void updateStatus(long shipmentId, String status, Timestamp deliveredAt) {
        jdbcTemplate.update(
            "UPDATE shipment SET status = ?, delivered_at = ?, updated_at = CURRENT_TIMESTAMP WHERE shipment_id = ?",
            status,
            deliveredAt,
            shipmentId
        );
    }

    public void insertShipmentEvent(long shipmentId, String eventType, Timestamp eventTime, String payloadJson) {
        jdbcTemplate.update(
            "INSERT INTO shipment_event (shipment_id, event_type, event_time, payload_json) VALUES (?, ?, ?, ?)",
            shipmentId,
            eventType,
            eventTime,
            payloadJson
        );
    }

    public List<Map<String, Object>> listShipmentEvents(long shipmentId) {
        return jdbcTemplate.queryForList(
            "SELECT shipment_event_id, shipment_id, event_type, event_time, payload_json FROM shipment_event "
                + "WHERE shipment_id = ? ORDER BY event_time",
            shipmentId
        );
    }

    public record ShipmentItemInsert(long shipmentId, long orderItemId, Long skuId, int qty) {
    }
}
