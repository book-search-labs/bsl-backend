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
public class PaymentRepository {
    private final JdbcTemplate jdbcTemplate;

    public PaymentRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Map<String, Object> findPayment(long paymentId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT payment_id, order_id, method, status, amount, currency, provider, provider_payment_id, "
                + "idempotency_key, failure_reason, pg_tx_id, created_at, updated_at FROM payment WHERE payment_id = ?",
            paymentId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Map<String, Object> findPaymentByIdempotencyKey(String idempotencyKey) {
        if (idempotencyKey == null) {
            return null;
        }
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT payment_id, order_id, method, status, amount, currency, provider, provider_payment_id, "
                + "idempotency_key, failure_reason, pg_tx_id, created_at, updated_at FROM payment WHERE idempotency_key = ?",
            idempotencyKey
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<Map<String, Object>> listPayments(int limit) {
        return jdbcTemplate.queryForList(
            "SELECT payment_id, order_id, method, status, amount, currency, provider, provider_payment_id, "
                + "idempotency_key, failure_reason, pg_tx_id, created_at, updated_at FROM payment ORDER BY payment_id DESC "
                + "LIMIT ?",
            limit
        );
    }

    public Map<String, Object> findLatestPaymentByOrder(long orderId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT payment_id, order_id, method, status, amount, currency, provider, provider_payment_id, "
                + "idempotency_key, failure_reason, pg_tx_id, created_at, updated_at FROM payment "
                + "WHERE order_id = ? ORDER BY payment_id DESC LIMIT 1",
            orderId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public long insertPayment(
        long orderId,
        String method,
        String status,
        int amount,
        String currency,
        String provider,
        String providerPaymentId,
        String idempotencyKey
    ) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO payment (order_id, method, status, amount, currency, provider, provider_payment_id, idempotency_key) "
                    + "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setLong(1, orderId);
            ps.setString(2, method);
            ps.setString(3, status);
            ps.setInt(4, amount);
            ps.setString(5, currency);
            ps.setString(6, provider);
            ps.setString(7, providerPaymentId);
            ps.setString(8, idempotencyKey);
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        return key == null ? 0L : key.longValue();
    }

    public void updatePaymentStatus(
        long paymentId,
        String status,
        String providerPaymentId,
        String failureReason
    ) {
        jdbcTemplate.update(
            "UPDATE payment SET status = ?, provider_payment_id = ?, failure_reason = ?, updated_at = CURRENT_TIMESTAMP "
                + "WHERE payment_id = ?",
            status,
            providerPaymentId,
            failureReason,
            paymentId
        );
    }

    public void insertPaymentEvent(long paymentId, String eventType, String providerEventId, String payloadJson) {
        jdbcTemplate.update(
            "INSERT INTO payment_event (payment_id, event_type, provider_event_id, payload_json) VALUES (?, ?, ?, ?)",
            paymentId,
            eventType,
            providerEventId,
            payloadJson
        );
    }
}
