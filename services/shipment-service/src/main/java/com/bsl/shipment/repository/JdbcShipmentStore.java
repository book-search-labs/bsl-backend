package com.bsl.shipment.repository;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcShipmentStore implements ShipmentStore {
    private final JdbcTemplate jdbcTemplate;

    public JdbcShipmentStore(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public Optional<IdempotencyRecord> findIdempotency(String idempotencyKey) {
        List<IdempotencyRecord> rows = jdbcTemplate.query(
            "SELECT * FROM idempotency_record WHERE idempotency_key = ?",
            (rs, rowNum) -> new IdempotencyRecord(
                rs.getString("idempotency_key"),
                rs.getString("operation_type"),
                rs.getString("request_hash"),
                rs.getString("status"),
                rs.getString("response_payload"),
                rs.getString("error_message")
            ),
            idempotencyKey
        );
        return rows.stream().findFirst();
    }

    @Override
    public void insertIdempotency(String idempotencyKey, String operationType, String requestHash, String status) {
        jdbcTemplate.update(
            "INSERT INTO idempotency_record (idempotency_key, operation_type, request_hash, status) VALUES (?, ?, ?, ?)",
            idempotencyKey,
            operationType,
            requestHash,
            status
        );
    }

    @Override
    public void updateIdempotencySucceeded(String idempotencyKey, String responsePayload) {
        jdbcTemplate.update(
            "UPDATE idempotency_record SET status = 'SUCCEEDED', response_payload = ?, updated_at = NOW(6) WHERE idempotency_key = ?",
            responsePayload,
            idempotencyKey
        );
    }

    @Override
    public void insertShipment(String shipmentId, long checkoutId, String orderId, String status, String idempotencyKey, String address, String responsePayload) {
        jdbcTemplate.update(
            "INSERT INTO shipment_request "
                + "(shipment_id, checkout_id, order_id, status, idempotency_key, address, response_payload) "
                + "VALUES (?, ?, ?, ?, ?, ?, ?)",
            shipmentId,
            checkoutId,
            orderId,
            status,
            idempotencyKey,
            address,
            responsePayload
        );
    }

    @Override
    public Optional<Map<String, Object>> findShipment(String shipmentId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT shipment_id, checkout_id, order_id, status, address FROM shipment_request WHERE shipment_id = ?",
            shipmentId
        );
        return rows.stream().findFirst();
    }

    @Override
    public int markShipmentCancelled(String shipmentId) {
        return jdbcTemplate.update(
            "UPDATE shipment_request SET status = 'CANCELLED', updated_at = NOW(6) WHERE shipment_id = ? AND status = 'REQUESTED'",
            shipmentId
        );
    }
}

