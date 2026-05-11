package com.bsl.order.repository;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcOrderStore implements OrderStore {
    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderStore(JdbcTemplate jdbcTemplate) {
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
    public void insertOrder(String orderId, String userId, long checkoutId, String status, BigDecimal totalAmount, String currency) {
        jdbcTemplate.update(
            "INSERT INTO orders (order_id, user_id, checkout_id, status, total_amount, currency) VALUES (?, ?, ?, ?, ?, ?)",
            orderId,
            userId,
            checkoutId,
            status,
            totalAmount,
            currency
        );
    }

    @Override
    public void insertOrderLine(String orderId, String bookId, String title, int quantity, BigDecimal unitPrice) {
        jdbcTemplate.update(
            "INSERT INTO order_lines (order_id, book_id, title, quantity, unit_price) VALUES (?, ?, ?, ?, ?)",
            orderId,
            bookId,
            title,
            quantity,
            unitPrice
        );
    }

    @Override
    public Optional<Map<String, Object>> findOrder(String orderId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT order_id, user_id, checkout_id, status, total_amount, currency, created_at, updated_at FROM orders WHERE order_id = ?",
            orderId
        );
        return rows.stream().findFirst();
    }

    @Override
    public List<Map<String, Object>> findOrderLines(String orderId) {
        return jdbcTemplate.queryForList(
            "SELECT book_id, title, quantity, unit_price FROM order_lines WHERE order_id = ? ORDER BY id ASC",
            orderId
        );
    }
}

