package com.bsl.commerce.repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class PaymentRepository {
    private static final String TABLE_PAYMENT = "payment";
    private static final String TABLE_PAYMENT_EVENT = "payment_event";
    private static final String TABLE_WEBHOOK_EVENT = "webhook_event";

    private static final String COLUMN_IDEMPOTENCY_KEY = "idempotency_key";
    private static final String COLUMN_FAILURE_REASON = "failure_reason";
    private static final String COLUMN_PG_TX_ID = "pg_tx_id";
    private static final String COLUMN_CHECKOUT_SESSION_ID = "checkout_session_id";
    private static final String COLUMN_RETURN_URL = "return_url";
    private static final String COLUMN_WEBHOOK_URL = "webhook_url";
    private static final String COLUMN_CHECKOUT_URL = "checkout_url";
    private static final String COLUMN_EXPIRES_AT = "expires_at";
    private static final String COLUMN_AUTHORIZED_AT = "authorized_at";
    private static final String COLUMN_CAPTURED_AT = "captured_at";
    private static final String COLUMN_FAILED_AT = "failed_at";
    private static final String COLUMN_CANCELED_AT = "canceled_at";
    private static final String COLUMN_RETRY_COUNT = "retry_count";
    private static final String COLUMN_LAST_RETRY_AT = "last_retry_at";
    private static final String COLUMN_NEXT_RETRY_AT = "next_retry_at";

    private final JdbcTemplate jdbcTemplate;

    private volatile Boolean hasIdempotencyKeyColumn;
    private volatile Boolean hasFailureReasonColumn;
    private volatile Boolean hasPgTxIdColumn;
    private volatile Boolean hasCheckoutSessionIdColumn;
    private volatile Boolean hasReturnUrlColumn;
    private volatile Boolean hasWebhookUrlColumn;
    private volatile Boolean hasCheckoutUrlColumn;
    private volatile Boolean hasExpiresAtColumn;
    private volatile Boolean hasAuthorizedAtColumn;
    private volatile Boolean hasCapturedAtColumn;
    private volatile Boolean hasFailedAtColumn;
    private volatile Boolean hasCanceledAtColumn;
    private volatile Boolean hasRetryCountColumn;
    private volatile Boolean hasLastRetryAtColumn;
    private volatile Boolean hasNextRetryAtColumn;
    private volatile Boolean hasPaymentEventTable;
    private volatile Boolean hasWebhookEventTable;

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

    public Map<String, Object> findPaymentByCheckoutSessionId(String checkoutSessionId) {
        if (checkoutSessionId == null || checkoutSessionId.isBlank() || !hasCheckoutSessionIdColumn()) {
            return null;
        }
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            paymentSelectSql() + " WHERE checkout_session_id = ?",
            checkoutSessionId
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

    public List<Map<String, Object>> listPayments(
        int limit,
        String status,
        String provider,
        LocalDate fromDate,
        LocalDate toDate
    ) {
        StringBuilder sql = new StringBuilder(paymentSelectSql()).append(" WHERE 1=1");
        List<Object> params = new ArrayList<>();
        if (status != null && !status.isBlank()) {
            sql.append(" AND status = ?");
            params.add(status);
        }
        if (provider != null && !provider.isBlank()) {
            sql.append(" AND provider = ?");
            params.add(provider);
        }
        if (fromDate != null) {
            sql.append(" AND DATE(created_at) >= ?");
            params.add(fromDate);
        }
        if (toDate != null) {
            sql.append(" AND DATE(created_at) <= ?");
            params.add(toDate);
        }
        sql.append(" ORDER BY payment_id DESC LIMIT ?");
        params.add(limit);
        return jdbcTemplate.queryForList(sql.toString(), params.toArray());
    }

    public List<Map<String, Object>> listWebhookEventsByPaymentId(long paymentId, int limit) {
        if (!hasWebhookEventTable()) {
            return List.of();
        }
        try {
            return jdbcTemplate.queryForList(
                webhookEventSelectSql() + " WHERE payment_id = ? ORDER BY webhook_event_id DESC LIMIT ?",
                paymentId,
                limit
            );
        } catch (BadSqlGrammarException ex) {
            hasWebhookEventTable = false;
            return List.of();
        }
    }

    public List<Map<String, Object>> listWebhookEvents(int limit, String processStatus, String provider) {
        if (!hasWebhookEventTable()) {
            return List.of();
        }
        try {
            StringBuilder sql = new StringBuilder(webhookEventSelectSql()).append(" WHERE 1=1");
            List<Object> params = new ArrayList<>();
            if (processStatus != null && !processStatus.isBlank()) {
                sql.append(" AND process_status = ?");
                params.add(processStatus);
            }
            if (provider != null && !provider.isBlank()) {
                sql.append(" AND provider = ?");
                params.add(provider);
            }
            sql.append(" ORDER BY webhook_event_id DESC LIMIT ?");
            params.add(limit);
            return jdbcTemplate.queryForList(sql.toString(), params.toArray());
        } catch (BadSqlGrammarException ex) {
            hasWebhookEventTable = false;
            return List.of();
        }
    }

    public Map<String, Object> findWebhookEventByEventId(String eventId) {
        if (!hasWebhookEventTable() || eventId == null || eventId.isBlank()) {
            return null;
        }
        try {
            List<Map<String, Object>> rows = jdbcTemplate.queryForList(
                webhookEventSelectSql() + " WHERE event_id = ? LIMIT 1",
                eventId
            );
            return rows.isEmpty() ? null : rows.get(0);
        } catch (BadSqlGrammarException ex) {
            hasWebhookEventTable = false;
            return null;
        }
    }

    public List<Map<String, Object>> listRetryableWebhookEvents(int limit, int maxRetryAttempts) {
        if (!hasWebhookEventTable()) {
            return List.of();
        }
        try {
            if (hasRetryCountColumn() && hasNextRetryAtColumn()) {
                return jdbcTemplate.queryForList(
                    webhookEventSelectSql()
                        + " WHERE signature_ok = 1 AND process_status = 'FAILED' "
                        + "AND retry_count < ? "
                        + "AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP) "
                        + "ORDER BY COALESCE(next_retry_at, received_at), webhook_event_id LIMIT ?",
                    maxRetryAttempts,
                    limit
                );
            }
            return jdbcTemplate.queryForList(
                webhookEventSelectSql()
                    + " WHERE signature_ok = 1 AND process_status = 'FAILED' "
                    + "ORDER BY webhook_event_id LIMIT ?",
                limit
            );
        } catch (BadSqlGrammarException ex) {
            hasWebhookEventTable = false;
            return List.of();
        }
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

    public void updateCheckoutContext(
        long paymentId,
        String checkoutSessionId,
        String returnUrl,
        String webhookUrl,
        String checkoutUrl,
        Instant expiresAt
    ) {
        if (
            !hasCheckoutSessionIdColumn()
                && !hasReturnUrlColumn()
                && !hasWebhookUrlColumn()
                && !hasCheckoutUrlColumn()
                && !hasExpiresAtColumn()
        ) {
            return;
        }
        StringBuilder sql = new StringBuilder("UPDATE payment SET updated_at = CURRENT_TIMESTAMP");
        List<Object> params = new ArrayList<>();
        if (hasCheckoutSessionIdColumn()) {
            sql.append(", checkout_session_id = ?");
            params.add(checkoutSessionId);
        }
        if (hasReturnUrlColumn()) {
            sql.append(", return_url = ?");
            params.add(returnUrl);
        }
        if (hasWebhookUrlColumn()) {
            sql.append(", webhook_url = ?");
            params.add(webhookUrl);
        }
        if (hasCheckoutUrlColumn()) {
            sql.append(", checkout_url = ?");
            params.add(checkoutUrl);
        }
        if (hasExpiresAtColumn()) {
            sql.append(", expires_at = ?");
            params.add(expiresAt == null ? null : Timestamp.from(expiresAt));
        }
        sql.append(" WHERE payment_id = ?");
        params.add(paymentId);
        jdbcTemplate.update(sql.toString(), params.toArray());
    }

    public void updatePaymentStatus(
        long paymentId,
        String status,
        String providerPaymentId,
        String failureReason
    ) {
        StringBuilder sql = new StringBuilder("UPDATE payment SET status = ?, provider_payment_id = ?");
        List<Object> params = new ArrayList<>();
        params.add(status);
        params.add(providerPaymentId);

        if (hasFailureReasonColumn()) {
            sql.append(", failure_reason = ?");
            params.add(failureReason);
        }
        if (hasAuthorizedAtColumn()) {
            sql.append(", authorized_at = CASE WHEN ? = 'AUTHORIZED' THEN CURRENT_TIMESTAMP ELSE authorized_at END");
            params.add(status);
        }
        if (hasCapturedAtColumn()) {
            sql.append(", captured_at = CASE WHEN ? = 'CAPTURED' THEN CURRENT_TIMESTAMP ELSE captured_at END");
            params.add(status);
        }
        if (hasFailedAtColumn()) {
            sql.append(", failed_at = CASE WHEN ? = 'FAILED' THEN CURRENT_TIMESTAMP ELSE failed_at END");
            params.add(status);
        }
        if (hasCanceledAtColumn()) {
            sql.append(", canceled_at = CASE WHEN ? = 'CANCELED' THEN CURRENT_TIMESTAMP ELSE canceled_at END");
            params.add(status);
        }

        sql.append(", updated_at = CURRENT_TIMESTAMP WHERE payment_id = ?");
        params.add(paymentId);

        jdbcTemplate.update(sql.toString(), params.toArray());
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

    public WebhookInsertResult insertWebhookEvent(
        String provider,
        String eventId,
        Long paymentId,
        boolean signatureOk,
        String payloadJson,
        String processStatus
    ) {
        if (!hasWebhookEventTable()) {
            return WebhookInsertResult.SKIPPED;
        }
        try {
            jdbcTemplate.update(
                "INSERT INTO webhook_event (provider, event_id, payment_id, signature_ok, payload_json, process_status) "
                    + "VALUES (?, ?, ?, ?, ?, ?)",
                provider,
                eventId,
                paymentId,
                signatureOk,
                payloadJson,
                processStatus
            );
            return WebhookInsertResult.INSERTED;
        } catch (DuplicateKeyException ex) {
            return WebhookInsertResult.DUPLICATE;
        } catch (BadSqlGrammarException ex) {
            hasWebhookEventTable = false;
            return WebhookInsertResult.SKIPPED;
        }
    }

    public void updateWebhookEventStatus(
        String eventId,
        boolean signatureOk,
        String processStatus,
        String errorMessage
    ) {
        if (!hasWebhookEventTable() || eventId == null || eventId.isBlank()) {
            return;
        }
        try {
            jdbcTemplate.update(
                "UPDATE webhook_event "
                    + "SET signature_ok = ?, process_status = ?, error_message = ?, processed_at = CURRENT_TIMESTAMP "
                    + "WHERE event_id = ?",
                signatureOk,
                processStatus,
                errorMessage,
                eventId
            );
        } catch (BadSqlGrammarException ex) {
            hasWebhookEventTable = false;
        }
    }

    public void markWebhookRetryAttempt(String eventId, int backoffSeconds, String note) {
        if (!hasWebhookEventTable() || eventId == null || eventId.isBlank()) {
            return;
        }
        if (!hasRetryCountColumn() && !hasLastRetryAtColumn() && !hasNextRetryAtColumn()) {
            return;
        }
        StringBuilder sql = new StringBuilder("UPDATE webhook_event SET ");
        List<Object> params = new ArrayList<>();
        boolean appended = false;

        if (hasRetryCountColumn()) {
            sql.append("retry_count = retry_count + 1");
            appended = true;
        }
        if (hasLastRetryAtColumn()) {
            if (appended) {
                sql.append(", ");
            }
            sql.append("last_retry_at = CURRENT_TIMESTAMP");
            appended = true;
        }
        if (hasNextRetryAtColumn()) {
            if (appended) {
                sql.append(", ");
            }
            sql.append("next_retry_at = CASE WHEN ? <= 0 THEN NULL ELSE DATE_ADD(CURRENT_TIMESTAMP, INTERVAL ? SECOND) END");
            params.add(backoffSeconds);
            params.add(backoffSeconds);
            appended = true;
        }
        if (note != null && !note.isBlank()) {
            if (appended) {
                sql.append(", ");
            }
            sql.append("error_message = CONCAT_WS(' | ', NULLIF(error_message, ''), ?)");
            params.add(note);
            appended = true;
        }
        if (!appended) {
            return;
        }
        sql.append(" WHERE event_id = ?");
        params.add(eventId);
        try {
            jdbcTemplate.update(sql.toString(), params.toArray());
        } catch (BadSqlGrammarException ex) {
            hasWebhookEventTable = false;
        }
    }

    public void markWebhookRetryResolved(String eventId, String processStatus, String note) {
        if (!hasWebhookEventTable() || eventId == null || eventId.isBlank()) {
            return;
        }
        StringBuilder sql = new StringBuilder(
            "UPDATE webhook_event SET process_status = ?, processed_at = CURRENT_TIMESTAMP, signature_ok = 1"
        );
        List<Object> params = new ArrayList<>();
        params.add(processStatus);

        if (hasNextRetryAtColumn()) {
            sql.append(", next_retry_at = NULL");
        }
        if (note != null && !note.isBlank()) {
            sql.append(", error_message = CONCAT_WS(' | ', NULLIF(error_message, ''), ?)");
            params.add(note);
        }
        sql.append(" WHERE event_id = ?");
        params.add(eventId);
        try {
            jdbcTemplate.update(sql.toString(), params.toArray());
        } catch (BadSqlGrammarException ex) {
            hasWebhookEventTable = false;
        }
    }

    private String paymentSelectSql() {
        return "SELECT payment_id, order_id, method, status, amount, currency, provider, provider_payment_id, "
            + optionalColumnExpr(COLUMN_IDEMPOTENCY_KEY, hasIdempotencyKeyColumn()) + ", "
            + optionalColumnExpr(COLUMN_FAILURE_REASON, hasFailureReasonColumn()) + ", "
            + optionalColumnExpr(COLUMN_PG_TX_ID, hasPgTxIdColumn()) + ", "
            + optionalColumnExpr(COLUMN_CHECKOUT_SESSION_ID, hasCheckoutSessionIdColumn()) + ", "
            + optionalColumnExpr(COLUMN_RETURN_URL, hasReturnUrlColumn()) + ", "
            + optionalColumnExpr(COLUMN_WEBHOOK_URL, hasWebhookUrlColumn()) + ", "
            + optionalColumnExpr(COLUMN_CHECKOUT_URL, hasCheckoutUrlColumn()) + ", "
            + optionalColumnExpr(COLUMN_EXPIRES_AT, hasExpiresAtColumn()) + ", "
            + optionalColumnExpr(COLUMN_AUTHORIZED_AT, hasAuthorizedAtColumn()) + ", "
            + optionalColumnExpr(COLUMN_CAPTURED_AT, hasCapturedAtColumn()) + ", "
            + optionalColumnExpr(COLUMN_FAILED_AT, hasFailedAtColumn()) + ", "
            + optionalColumnExpr(COLUMN_CANCELED_AT, hasCanceledAtColumn()) + ", "
            + "created_at, updated_at FROM payment";
    }

    private String webhookEventSelectSql() {
        return "SELECT webhook_event_id, provider, event_id, payment_id, signature_ok, received_at, processed_at, "
            + "process_status, error_message, payload_json, "
            + optionalColumnExpr(COLUMN_RETRY_COUNT, hasRetryCountColumn()) + ", "
            + optionalColumnExpr(COLUMN_LAST_RETRY_AT, hasLastRetryAtColumn()) + ", "
            + optionalColumnExpr(COLUMN_NEXT_RETRY_AT, hasNextRetryAtColumn()) + " "
            + "FROM webhook_event";
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

    private boolean hasCheckoutSessionIdColumn() {
        Boolean cached = hasCheckoutSessionIdColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasCheckoutSessionIdColumn == null) {
                hasCheckoutSessionIdColumn = hasColumn(TABLE_PAYMENT, COLUMN_CHECKOUT_SESSION_ID);
            }
            return hasCheckoutSessionIdColumn;
        }
    }

    private boolean hasReturnUrlColumn() {
        Boolean cached = hasReturnUrlColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasReturnUrlColumn == null) {
                hasReturnUrlColumn = hasColumn(TABLE_PAYMENT, COLUMN_RETURN_URL);
            }
            return hasReturnUrlColumn;
        }
    }

    private boolean hasWebhookUrlColumn() {
        Boolean cached = hasWebhookUrlColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasWebhookUrlColumn == null) {
                hasWebhookUrlColumn = hasColumn(TABLE_PAYMENT, COLUMN_WEBHOOK_URL);
            }
            return hasWebhookUrlColumn;
        }
    }

    private boolean hasCheckoutUrlColumn() {
        Boolean cached = hasCheckoutUrlColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasCheckoutUrlColumn == null) {
                hasCheckoutUrlColumn = hasColumn(TABLE_PAYMENT, COLUMN_CHECKOUT_URL);
            }
            return hasCheckoutUrlColumn;
        }
    }

    private boolean hasExpiresAtColumn() {
        Boolean cached = hasExpiresAtColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasExpiresAtColumn == null) {
                hasExpiresAtColumn = hasColumn(TABLE_PAYMENT, COLUMN_EXPIRES_AT);
            }
            return hasExpiresAtColumn;
        }
    }

    private boolean hasAuthorizedAtColumn() {
        Boolean cached = hasAuthorizedAtColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasAuthorizedAtColumn == null) {
                hasAuthorizedAtColumn = hasColumn(TABLE_PAYMENT, COLUMN_AUTHORIZED_AT);
            }
            return hasAuthorizedAtColumn;
        }
    }

    private boolean hasCapturedAtColumn() {
        Boolean cached = hasCapturedAtColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasCapturedAtColumn == null) {
                hasCapturedAtColumn = hasColumn(TABLE_PAYMENT, COLUMN_CAPTURED_AT);
            }
            return hasCapturedAtColumn;
        }
    }

    private boolean hasFailedAtColumn() {
        Boolean cached = hasFailedAtColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasFailedAtColumn == null) {
                hasFailedAtColumn = hasColumn(TABLE_PAYMENT, COLUMN_FAILED_AT);
            }
            return hasFailedAtColumn;
        }
    }

    private boolean hasCanceledAtColumn() {
        Boolean cached = hasCanceledAtColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasCanceledAtColumn == null) {
                hasCanceledAtColumn = hasColumn(TABLE_PAYMENT, COLUMN_CANCELED_AT);
            }
            return hasCanceledAtColumn;
        }
    }

    private boolean hasRetryCountColumn() {
        Boolean cached = hasRetryCountColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasRetryCountColumn == null) {
                hasRetryCountColumn = hasColumn(TABLE_WEBHOOK_EVENT, COLUMN_RETRY_COUNT);
            }
            return hasRetryCountColumn;
        }
    }

    private boolean hasLastRetryAtColumn() {
        Boolean cached = hasLastRetryAtColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasLastRetryAtColumn == null) {
                hasLastRetryAtColumn = hasColumn(TABLE_WEBHOOK_EVENT, COLUMN_LAST_RETRY_AT);
            }
            return hasLastRetryAtColumn;
        }
    }

    private boolean hasNextRetryAtColumn() {
        Boolean cached = hasNextRetryAtColumn;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasNextRetryAtColumn == null) {
                hasNextRetryAtColumn = hasColumn(TABLE_WEBHOOK_EVENT, COLUMN_NEXT_RETRY_AT);
            }
            return hasNextRetryAtColumn;
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

    private boolean hasWebhookEventTable() {
        Boolean cached = hasWebhookEventTable;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasWebhookEventTable == null) {
                hasWebhookEventTable = hasTable(TABLE_WEBHOOK_EVENT);
            }
            return hasWebhookEventTable;
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

    public enum WebhookInsertResult {
        INSERTED,
        DUPLICATE,
        SKIPPED
    }
}
