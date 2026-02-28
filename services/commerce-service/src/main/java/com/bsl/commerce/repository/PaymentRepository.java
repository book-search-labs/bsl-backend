package com.bsl.commerce.repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class PaymentRepository {
    private static final String TABLE_PAYMENT = "payment";
    private static final String TABLE_PAYMENT_EVENT = "payment_event";
    private static final String COLUMN_IDEMPOTENCY_KEY = "idempotency_key";
    private static final String COLUMN_FAILURE_REASON = "failure_reason";
    private static final String COLUMN_PG_TX_ID = "pg_tx_id";

    private final JdbcTemplate jdbcTemplate;
    private volatile Boolean hasIdempotencyKeyColumn;
    private volatile Boolean hasFailureReasonColumn;
    private volatile Boolean hasPgTxIdColumn;
    private volatile Boolean hasPaymentEventTable;

    public PaymentRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Map<String, Object> findPayment(long paymentId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            paymentSelectSql() + " WHERE payment_id = ?",
            paymentId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Map<String, Object> findPaymentByIdempotencyKey(String idempotencyKey) {
        if (idempotencyKey == null || !hasIdempotencyKeyColumn()) {
            return null;
        }
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            paymentSelectSql() + " WHERE idempotency_key = ?",
            idempotencyKey
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<Map<String, Object>> listPayments(int limit) {
        return jdbcTemplate.queryForList(
            paymentSelectSql() + " ORDER BY payment_id DESC LIMIT ?",
            limit
        );
    }

    public Map<String, Object> findLatestPaymentByOrder(long orderId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            paymentSelectSql() + " WHERE order_id = ? ORDER BY payment_id DESC LIMIT 1",
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
        boolean idempotencyKeySupported = hasIdempotencyKeyColumn();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                idempotencyKeySupported
                    ? "INSERT INTO payment (order_id, method, status, amount, currency, provider, provider_payment_id, idempotency_key) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                    : "INSERT INTO payment (order_id, method, status, amount, currency, provider, provider_payment_id) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setLong(1, orderId);
            ps.setString(2, method);
            ps.setString(3, status);
            ps.setInt(4, amount);
            ps.setString(5, currency);
            ps.setString(6, provider);
            ps.setString(7, providerPaymentId);
            if (idempotencyKeySupported) {
                ps.setString(8, idempotencyKey);
            }
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
        if (hasFailureReasonColumn()) {
            jdbcTemplate.update(
                "UPDATE payment SET status = ?, provider_payment_id = ?, failure_reason = ?, updated_at = CURRENT_TIMESTAMP "
                    + "WHERE payment_id = ?",
                status,
                providerPaymentId,
                failureReason,
                paymentId
            );
            return;
        }
        jdbcTemplate.update(
            "UPDATE payment SET status = ?, provider_payment_id = ?, updated_at = CURRENT_TIMESTAMP "
                + "WHERE payment_id = ?",
            status,
            providerPaymentId,
            paymentId
        );
    }

    public void insertPaymentEvent(long paymentId, String eventType, String providerEventId, String payloadJson) {
        if (!hasPaymentEventTable()) {
            return;
        }
        try {
            jdbcTemplate.update(
                "INSERT INTO payment_event (payment_id, event_type, provider_event_id, payload_json) VALUES (?, ?, ?, ?)",
                paymentId,
                eventType,
                providerEventId,
                payloadJson
            );
        } catch (BadSqlGrammarException ex) {
            hasPaymentEventTable = false;
        }
    }

    private String paymentSelectSql() {
        return "SELECT payment_id, order_id, method, status, amount, currency, provider, provider_payment_id, "
            + optionalColumnExpr(COLUMN_IDEMPOTENCY_KEY, hasIdempotencyKeyColumn()) + ", "
            + optionalColumnExpr(COLUMN_FAILURE_REASON, hasFailureReasonColumn()) + ", "
            + optionalColumnExpr(COLUMN_PG_TX_ID, hasPgTxIdColumn()) + ", "
            + "created_at, updated_at FROM payment";
    }

    private String optionalColumnExpr(String columnName, boolean supported) {
        return supported ? columnName : "NULL AS " + columnName;
    }

    private boolean hasIdempotencyKeyColumn() {
        Boolean cached = hasIdempotencyKeyColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasIdempotencyKeyColumn == null) {
                hasIdempotencyKeyColumn = hasColumn(TABLE_PAYMENT, COLUMN_IDEMPOTENCY_KEY);
            }
            return hasIdempotencyKeyColumn;
        }
    }

    private boolean hasFailureReasonColumn() {
        Boolean cached = hasFailureReasonColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasFailureReasonColumn == null) {
                hasFailureReasonColumn = hasColumn(TABLE_PAYMENT, COLUMN_FAILURE_REASON);
            }
            return hasFailureReasonColumn;
        }
    }

    private boolean hasPgTxIdColumn() {
        Boolean cached = hasPgTxIdColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasPgTxIdColumn == null) {
                hasPgTxIdColumn = hasColumn(TABLE_PAYMENT, COLUMN_PG_TX_ID);
            }
            return hasPgTxIdColumn;
        }
    }

    private boolean hasPaymentEventTable() {
        Boolean cached = hasPaymentEventTable;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasPaymentEventTable == null) {
                hasPaymentEventTable = hasTable(TABLE_PAYMENT_EVENT);
            }
            return hasPaymentEventTable;
        }
    }

    private boolean hasColumn(String tableName, String columnName) {
        try {
            Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM information_schema.columns "
                    + "WHERE table_schema = DATABASE() AND table_name = ? AND column_name = ?",
                Integer.class,
                tableName,
                columnName
            );
            return count != null && count > 0;
        } catch (Exception ex) {
            return false;
        }
    }

    private boolean hasTable(String tableName) {
        try {
            Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM information_schema.tables "
                    + "WHERE table_schema = DATABASE() AND table_name = ?",
                Integer.class,
                tableName
            );
            return count != null && count > 0;
        } catch (Exception ex) {
            return false;
        }
    }
}
