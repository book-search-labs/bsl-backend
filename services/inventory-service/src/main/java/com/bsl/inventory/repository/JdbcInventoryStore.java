package com.bsl.inventory.repository;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcInventoryStore implements InventoryStore {
    private final JdbcTemplate jdbcTemplate;

    public JdbcInventoryStore(JdbcTemplate jdbcTemplate) {
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
    public int reserveStock(String bookId, int quantity) {
        return jdbcTemplate.update(
            "UPDATE book_stock "
                + "SET available_quantity = available_quantity - ?, reserved_quantity = reserved_quantity + ?, version = version + 1, updated_at = NOW(6) "
                + "WHERE book_id = ? AND available_quantity >= ?",
            quantity,
            quantity,
            bookId,
            quantity
        );
    }

    @Override
    public int releaseStock(String bookId, int quantity) {
        return jdbcTemplate.update(
            "UPDATE book_stock "
                + "SET available_quantity = available_quantity + ?, reserved_quantity = reserved_quantity - ?, version = version + 1, updated_at = NOW(6) "
                + "WHERE book_id = ? AND reserved_quantity >= ?",
            quantity,
            quantity,
            bookId,
            quantity
        );
    }

    @Override
    public void insertReservation(String reservationId, long checkoutId, String orderId, String status, String idempotencyKey, String responsePayload) {
        jdbcTemplate.update(
            "INSERT INTO inventory_reservation "
                + "(reservation_id, checkout_id, order_id, status, idempotency_key, response_payload) VALUES (?, ?, ?, ?, ?, ?)",
            reservationId,
            checkoutId,
            orderId,
            status,
            idempotencyKey,
            responsePayload
        );
    }

    @Override
    public void insertReservationLine(String reservationId, String bookId, int quantity) {
        jdbcTemplate.update(
            "INSERT INTO inventory_reservation_line (reservation_id, book_id, quantity) VALUES (?, ?, ?)",
            reservationId,
            bookId,
            quantity
        );
    }

    @Override
    public Optional<Map<String, Object>> findReservation(String reservationId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT reservation_id, checkout_id, order_id, status FROM inventory_reservation WHERE reservation_id = ?",
            reservationId
        );
        return rows.stream().findFirst();
    }

    @Override
    public List<Map<String, Object>> findReservationLines(String reservationId) {
        return jdbcTemplate.queryForList(
            "SELECT book_id, quantity FROM inventory_reservation_line WHERE reservation_id = ? ORDER BY id ASC",
            reservationId
        );
    }

    @Override
    public int markReservationReleased(String reservationId) {
        return jdbcTemplate.update(
            "UPDATE inventory_reservation SET status = 'RELEASED', updated_at = NOW(6) WHERE reservation_id = ? AND status = 'RESERVED'",
            reservationId
        );
    }
}

