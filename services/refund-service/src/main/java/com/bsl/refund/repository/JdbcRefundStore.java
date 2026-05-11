package com.bsl.refund.repository;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcRefundStore implements RefundStore {
    private final JdbcTemplate jdbcTemplate;

    public JdbcRefundStore(JdbcTemplate jdbcTemplate) {
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
    public void markIdempotencyProcessing(String idempotencyKey) {
        jdbcTemplate.update(
            "UPDATE idempotency_record SET status = 'PROCESSING', error_message = NULL, updated_at = NOW(6) WHERE idempotency_key = ?",
            idempotencyKey
        );
    }

    @Override
    public void updateIdempotencySucceeded(String idempotencyKey, String responsePayload) {
        jdbcTemplate.update(
            "UPDATE idempotency_record SET status = 'SUCCEEDED', response_payload = ?, error_message = NULL, updated_at = NOW(6) "
                + "WHERE idempotency_key = ?",
            responsePayload,
            idempotencyKey
        );
    }

    @Override
    public void updateIdempotencyFailed(String idempotencyKey, String errorMessage) {
        jdbcTemplate.update(
            "UPDATE idempotency_record SET status = 'FAILED', error_message = ?, updated_at = NOW(6) WHERE idempotency_key = ?",
            errorMessage,
            idempotencyKey
        );
    }

    @Override
    public void insertRefund(
        String refundId,
        String orderId,
        long checkoutId,
        String userId,
        String paymentId,
        String inventoryReservationId,
        String status,
        String reason,
        BigDecimal totalAmount,
        String currency,
        String requestPayload,
        String responsePayload
    ) {
        jdbcTemplate.update(
            "INSERT INTO refund "
                + "(refund_id, order_id, checkout_id, user_id, payment_id, inventory_reservation_id, status, reason, "
                + "total_amount, currency, request_payload, response_payload) "
                + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            refundId,
            orderId,
            checkoutId,
            userId,
            paymentId,
            inventoryReservationId,
            status,
            reason,
            totalAmount,
            currency,
            requestPayload,
            responsePayload
        );
    }

    @Override
    public void insertRefundItem(String refundId, String bookId, int quantity, BigDecimal amount) {
        jdbcTemplate.update(
            "INSERT INTO refund_item (refund_id, book_id, quantity, amount) VALUES (?, ?, ?, ?)",
            refundId,
            bookId,
            quantity,
            amount
        );
    }

    @Override
    public Optional<RefundRecord> findRefund(String refundId) {
        List<RefundRecord> rows = jdbcTemplate.query(
            "SELECT * FROM refund WHERE refund_id = ?",
            (rs, rowNum) -> refundRecord(rs.getLong("id"),
                rs.getString("refund_id"),
                rs.getString("order_id"),
                rs.getLong("checkout_id"),
                rs.getString("user_id"),
                rs.getString("payment_id"),
                rs.getString("inventory_reservation_id"),
                rs.getString("status"),
                rs.getString("reason"),
                rs.getBigDecimal("total_amount"),
                rs.getString("currency"),
                rs.getString("request_payload"),
                rs.getString("response_payload"),
                rs.getString("error_message")),
            refundId
        );
        return rows.stream().findFirst();
    }

    @Override
    public List<RefundRecord> findRefundsByOrderId(String orderId) {
        return jdbcTemplate.query(
            "SELECT * FROM refund WHERE order_id = ? ORDER BY id DESC",
            (rs, rowNum) -> refundRecord(
                rs.getLong("id"),
                rs.getString("refund_id"),
                rs.getString("order_id"),
                rs.getLong("checkout_id"),
                rs.getString("user_id"),
                rs.getString("payment_id"),
                rs.getString("inventory_reservation_id"),
                rs.getString("status"),
                rs.getString("reason"),
                rs.getBigDecimal("total_amount"),
                rs.getString("currency"),
                rs.getString("request_payload"),
                rs.getString("response_payload"),
                rs.getString("error_message")
            ),
            orderId
        );
    }

    @Override
    public List<RefundRecord> findAllRefunds() {
        return jdbcTemplate.query(
            "SELECT * FROM refund ORDER BY id DESC LIMIT 200",
            (rs, rowNum) -> refundRecord(
                rs.getLong("id"),
                rs.getString("refund_id"),
                rs.getString("order_id"),
                rs.getLong("checkout_id"),
                rs.getString("user_id"),
                rs.getString("payment_id"),
                rs.getString("inventory_reservation_id"),
                rs.getString("status"),
                rs.getString("reason"),
                rs.getBigDecimal("total_amount"),
                rs.getString("currency"),
                rs.getString("request_payload"),
                rs.getString("response_payload"),
                rs.getString("error_message")
            )
        );
    }

    @Override
    public List<RefundItem> findRefundItems(String refundId) {
        return jdbcTemplate.query(
            "SELECT * FROM refund_item WHERE refund_id = ? ORDER BY id ASC",
            (rs, rowNum) -> new RefundItem(
                rs.getString("refund_id"),
                rs.getString("book_id"),
                rs.getInt("quantity"),
                rs.getBigDecimal("amount")
            ),
            refundId
        );
    }

    @Override
    public void updateRefundStatus(String refundId, String status, String responsePayload, String errorMessage) {
        jdbcTemplate.update(
            "UPDATE refund SET status = ?, response_payload = ?, error_message = ?, version = version + 1, updated_at = NOW(6) "
                + "WHERE refund_id = ?",
            status,
            responsePayload,
            errorMessage,
            refundId
        );
    }

    @Override
    public void insertRefundEvent(String refundId, String eventType, String payload) {
        jdbcTemplate.update(
            "INSERT INTO refund_event (refund_id, event_type, payload) VALUES (?, ?, ?)",
            refundId,
            eventType,
            payload
        );
    }

    @Override
    public void insertOutboxEvent(String aggregateId, String eventType, String eventKey, String payload) {
        jdbcTemplate.update(
            "INSERT INTO outbox_event (aggregate_type, aggregate_id, event_type, event_key, payload, status) "
                + "VALUES ('REFUND', ?, ?, ?, ?, 'READY')",
            aggregateId,
            eventType,
            eventKey,
            payload
        );
    }

    private RefundRecord refundRecord(
        long id,
        String refundId,
        String orderId,
        long checkoutId,
        String userId,
        String paymentId,
        String inventoryReservationId,
        String status,
        String reason,
        BigDecimal totalAmount,
        String currency,
        String requestPayload,
        String responsePayload,
        String errorMessage
    ) {
        return new RefundRecord(
            id,
            refundId,
            orderId,
            checkoutId,
            userId,
            paymentId,
            inventoryReservationId,
            status,
            reason,
            totalAmount,
            currency,
            requestPayload,
            responsePayload,
            errorMessage
        );
    }
}
