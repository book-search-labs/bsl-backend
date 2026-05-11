package com.bsl.payment.repository;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcPaymentStore implements PaymentStore {
    private final JdbcTemplate jdbcTemplate;

    public JdbcPaymentStore(JdbcTemplate jdbcTemplate) {
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
    public void insertAuthorization(
        String paymentId,
        long checkoutId,
        String orderId,
        BigDecimal amount,
        String currency,
        String status,
        String idempotencyKey,
        String pgTransactionId,
        String responsePayload
    ) {
        jdbcTemplate.update(
            "INSERT INTO payment_authorization "
                + "(payment_id, checkout_id, order_id, amount, currency, status, idempotency_key, pg_transaction_id, response_payload) "
                + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            paymentId,
            checkoutId,
            orderId,
            amount,
            currency,
            status,
            idempotencyKey,
            pgTransactionId,
            responsePayload
        );
    }

    @Override
    public void insertCancellation(
        String cancellationId,
        String paymentId,
        long checkoutId,
        String status,
        String idempotencyKey,
        String responsePayload
    ) {
        jdbcTemplate.update(
            "INSERT INTO payment_cancellation "
                + "(cancellation_id, payment_id, checkout_id, status, idempotency_key, response_payload) "
                + "VALUES (?, ?, ?, ?, ?, ?)",
            cancellationId,
            paymentId,
            checkoutId,
            status,
            idempotencyKey,
            responsePayload
        );
    }
}

