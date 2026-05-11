package com.bsl.checkoutorchestrator.repository;

import com.bsl.checkoutorchestrator.domain.CheckoutSagaStatus;
import com.bsl.checkoutorchestrator.domain.CheckoutStepCategory;
import com.bsl.checkoutorchestrator.domain.CheckoutStepName;
import com.bsl.checkoutorchestrator.domain.CheckoutStepStatus;
import com.bsl.checkoutorchestrator.domain.OutboxStatus;
import com.bsl.checkoutorchestrator.domain.RecoveryPolicy;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcCheckoutSagaStore implements CheckoutSagaStore {
    private final JdbcTemplate jdbcTemplate;

    public JdbcCheckoutSagaStore(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public Optional<SagaRecord> findSagaByCheckoutKey(String checkoutKey) {
        List<SagaRecord> rows = jdbcTemplate.query(
            "SELECT * FROM checkout_saga WHERE checkout_key = ?",
            this::mapSaga,
            checkoutKey
        );
        return rows.stream().findFirst();
    }

    @Override
    public Optional<SagaRecord> findSagaById(long checkoutId) {
        List<SagaRecord> rows = jdbcTemplate.query(
            "SELECT * FROM checkout_saga WHERE id = ?",
            this::mapSaga,
            checkoutId
        );
        return rows.stream().findFirst();
    }

    @Override
    public List<SagaRecord> findSagas(CheckoutSagaStatus status, int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 200));
        if (status == null) {
            return jdbcTemplate.query(
                "SELECT * FROM checkout_saga ORDER BY updated_at DESC, id DESC LIMIT ?",
                this::mapSaga,
                safeLimit
            );
        }
        return jdbcTemplate.query(
            "SELECT * FROM checkout_saga WHERE status = ? ORDER BY updated_at DESC, id DESC LIMIT ?",
            this::mapSaga,
            status.name(),
            safeLimit
        );
    }

    @Override
    public List<StepRecord> findStepsBySagaId(long checkoutSagaId) {
        return jdbcTemplate.query(
            "SELECT * FROM checkout_saga_step WHERE checkout_saga_id = ? ORDER BY id ASC",
            this::mapStep,
            checkoutSagaId
        );
    }

    @Override
    public List<OutboxEventRecord> findOutboxEventsByAggregate(String aggregateType, long aggregateId) {
        return jdbcTemplate.query(
            "SELECT * FROM outbox_event WHERE aggregate_type = ? AND aggregate_id = ? ORDER BY id ASC",
            this::mapOutboxEvent,
            aggregateType,
            aggregateId
        );
    }

    @Override
    public List<StepRecord> findDueSteps(Instant now, int limit) {
        return jdbcTemplate.query(
            "SELECT step.* FROM checkout_saga_step step "
                + "JOIN checkout_saga saga ON saga.id = step.checkout_saga_id "
                + "WHERE step.status IN ('READY', 'FAILED_RETRYING', 'UNKNOWN') "
                + "AND (step.next_retry_at IS NULL OR step.next_retry_at <= ?) "
                + "AND saga.status IN ('PENDING', 'PROCESSING', 'FAILED_RETRYING') "
                + "ORDER BY step.checkout_saga_id ASC, step.id ASC "
                + "LIMIT ?",
            this::mapStep,
            Timestamp.from(now),
            limit
        );
    }

    @Override
    public Optional<StepRecord> findStepById(long stepId) {
        List<StepRecord> rows = jdbcTemplate.query(
            "SELECT * FROM checkout_saga_step WHERE id = ?",
            this::mapStep,
            stepId
        );
        return rows.stream().findFirst();
    }

    @Override
    public Optional<StepRecord> findStepBySagaIdAndName(long checkoutSagaId, CheckoutStepName stepName) {
        List<StepRecord> rows = jdbcTemplate.query(
            "SELECT * FROM checkout_saga_step WHERE checkout_saga_id = ? AND step_name = ?",
            this::mapStep,
            checkoutSagaId,
            stepName.name()
        );
        return rows.stream().findFirst();
    }

    @Override
    public long insertSaga(NewSagaRecord saga) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO checkout_saga "
                    + "(checkout_key, user_id, status, current_step, request_payload, context_payload, error_code, "
                    + "error_message, version, created_at, updated_at) "
                    + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setString(1, saga.checkoutKey());
            ps.setString(2, saga.userId());
            ps.setString(3, saga.status().name());
            ps.setString(4, saga.currentStep());
            ps.setString(5, saga.requestPayload());
            ps.setString(6, saga.contextPayload());
            ps.setString(7, saga.errorCode());
            ps.setString(8, saga.errorMessage());
            ps.setLong(9, saga.version());
            ps.setTimestamp(10, Timestamp.from(saga.createdAt()));
            ps.setTimestamp(11, Timestamp.from(saga.updatedAt()));
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        if (key == null) {
            throw new IllegalStateException("checkout_saga generated key is missing");
        }
        return key.longValue();
    }

    @Override
    public void insertStep(NewStepRecord step) {
        jdbcTemplate.update(
            "INSERT INTO checkout_saga_step "
                + "(checkout_saga_id, step_name, status, step_category, recovery_policy, idempotency_key, "
                + "request_payload, response_payload, retry_count, max_retry_count, next_retry_at, error_code, "
                + "error_message, external_reference_type, external_reference_id, started_at, completed_at, "
                + "created_at, updated_at) "
                + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            step.checkoutSagaId(),
            step.stepName().name(),
            step.status().name(),
            step.stepCategory().name(),
            step.recoveryPolicy().name(),
            step.idempotencyKey(),
            step.requestPayload(),
            step.responsePayload(),
            step.retryCount(),
            step.maxRetryCount(),
            timestamp(step.nextRetryAt()),
            step.errorCode(),
            step.errorMessage(),
            step.externalReferenceType(),
            step.externalReferenceId(),
            timestamp(step.startedAt()),
            timestamp(step.completedAt()),
            Timestamp.from(step.createdAt()),
            Timestamp.from(step.updatedAt())
        );
    }

    @Override
    public void insertOutboxEvent(NewOutboxEventRecord event) {
        jdbcTemplate.update(
            "INSERT INTO outbox_event "
                + "(aggregate_type, aggregate_id, event_type, event_key, payload, status, retry_count, "
                + "next_retry_at, locked_by, locked_until, error_message, created_at, updated_at, published_at) "
                + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            event.aggregateType(),
            event.aggregateId(),
            event.eventType(),
            event.eventKey(),
            event.payload(),
            event.status().name(),
            event.retryCount(),
            timestamp(event.nextRetryAt()),
            event.lockedBy(),
            timestamp(event.lockedUntil()),
            event.errorMessage(),
            Timestamp.from(event.createdAt()),
            Timestamp.from(event.updatedAt()),
            timestamp(event.publishedAt())
        );
    }

    @Override
    public boolean outboxEventExists(String eventKey) {
        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM outbox_event WHERE event_key = ?",
            Integer.class,
            eventKey
        );
        return count != null && count > 0;
    }

    @Override
    public int claimStepForProcessing(long stepId, CheckoutStepStatus expectedStatus, Instant now) {
        return jdbcTemplate.update(
            "UPDATE checkout_saga_step "
                + "SET status = 'PROCESSING', started_at = COALESCE(started_at, ?), updated_at = ? "
                + "WHERE id = ? AND status = ? AND (next_retry_at IS NULL OR next_retry_at <= ?)",
            Timestamp.from(now),
            Timestamp.from(now),
            stepId,
            expectedStatus.name(),
            Timestamp.from(now)
        );
    }

    @Override
    public void updateSagaStatus(
        long sagaId,
        CheckoutSagaStatus status,
        CheckoutStepName currentStep,
        String errorCode,
        String errorMessage,
        Instant now
    ) {
        jdbcTemplate.update(
            "UPDATE checkout_saga "
                + "SET status = ?, current_step = ?, error_code = ?, error_message = ?, version = version + 1, updated_at = ? "
                + "WHERE id = ?",
            status.name(),
            currentStep == null ? null : currentStep.name(),
            errorCode,
            errorMessage,
            Timestamp.from(now),
            sagaId
        );
    }

    @Override
    public void updateSagaContext(long sagaId, String contextPayload, Instant now) {
        jdbcTemplate.update(
            "UPDATE checkout_saga SET context_payload = ?, version = version + 1, updated_at = ? WHERE id = ?",
            contextPayload,
            Timestamp.from(now),
            sagaId
        );
    }

    @Override
    public void markStepSucceeded(long stepId, String responsePayload, Instant now) {
        jdbcTemplate.update(
            "UPDATE checkout_saga_step "
                + "SET status = 'SUCCEEDED', response_payload = ?, error_code = NULL, error_message = NULL, "
                + "next_retry_at = NULL, completed_at = ?, updated_at = ? WHERE id = ?",
            responsePayload,
            Timestamp.from(now),
            Timestamp.from(now),
            stepId
        );
    }

    @Override
    public void markStepFailedRetrying(
        long stepId,
        int retryCount,
        Instant nextRetryAt,
        String errorCode,
        String errorMessage,
        Instant now
    ) {
        jdbcTemplate.update(
            "UPDATE checkout_saga_step "
                + "SET status = 'FAILED_RETRYING', retry_count = ?, next_retry_at = ?, error_code = ?, error_message = ?, updated_at = ? "
                + "WHERE id = ?",
            retryCount,
            timestamp(nextRetryAt),
            errorCode,
            errorMessage,
            Timestamp.from(now),
            stepId
        );
    }

    @Override
    public void markStepUnknown(
        long stepId,
        int retryCount,
        Instant nextRetryAt,
        String errorCode,
        String errorMessage,
        Instant now
    ) {
        jdbcTemplate.update(
            "UPDATE checkout_saga_step "
                + "SET status = 'UNKNOWN', retry_count = ?, next_retry_at = ?, error_code = ?, error_message = ?, updated_at = ? "
                + "WHERE id = ?",
            retryCount,
            timestamp(nextRetryAt),
            errorCode,
            errorMessage,
            Timestamp.from(now),
            stepId
        );
    }

    @Override
    public void markStepManualReview(long stepId, String errorCode, String errorMessage, Instant now) {
        jdbcTemplate.update(
            "UPDATE checkout_saga_step "
                + "SET status = 'MANUAL_REVIEW_REQUIRED', error_code = ?, error_message = ?, next_retry_at = NULL, updated_at = ? "
                + "WHERE id = ?",
            errorCode,
            errorMessage,
            Timestamp.from(now),
            stepId
        );
    }

    @Override
    public void resetStepForManualRetry(long stepId, Instant now) {
        jdbcTemplate.update(
            "UPDATE checkout_saga_step "
                + "SET status = 'READY', next_retry_at = NULL, error_code = NULL, error_message = NULL, updated_at = ? "
                + "WHERE id = ? AND status IN ('FAILED_RETRYING', 'MANUAL_REVIEW_REQUIRED')",
            Timestamp.from(now),
            stepId
        );
    }

    @Override
    public void scheduleUnknownReconciliation(long stepId, Instant now) {
        jdbcTemplate.update(
            "UPDATE checkout_saga_step SET next_retry_at = NULL, updated_at = ? WHERE id = ? AND status = 'UNKNOWN'",
            Timestamp.from(now),
            stepId
        );
    }

    @Override
    public void markStepCompensating(long stepId, Instant now) {
        jdbcTemplate.update(
            "UPDATE checkout_saga_step SET status = 'COMPENSATING', updated_at = ? WHERE id = ? AND status = 'SUCCEEDED'",
            Timestamp.from(now),
            stepId
        );
    }

    @Override
    public void markStepCompensated(long stepId, String responsePayload, Instant now) {
        jdbcTemplate.update(
            "UPDATE checkout_saga_step "
                + "SET status = 'COMPENSATED', response_payload = ?, error_code = NULL, error_message = NULL, completed_at = ?, updated_at = ? "
                + "WHERE id = ?",
            responsePayload,
            Timestamp.from(now),
            Timestamp.from(now),
            stepId
        );
    }

    @Override
    public void markStepCompensationFailed(long stepId, String errorCode, String errorMessage, Instant now) {
        jdbcTemplate.update(
            "UPDATE checkout_saga_step SET error_code = ?, error_message = ?, updated_at = ? WHERE id = ?",
            errorCode,
            errorMessage,
            Timestamp.from(now),
            stepId
        );
    }

    private SagaRecord mapSaga(ResultSet rs, int rowNum) throws java.sql.SQLException {
        return new SagaRecord(
            rs.getLong("id"),
            rs.getString("checkout_key"),
            rs.getString("user_id"),
            CheckoutSagaStatus.valueOf(rs.getString("status")),
            rs.getString("current_step"),
            rs.getString("request_payload"),
            rs.getString("context_payload"),
            rs.getString("error_code"),
            rs.getString("error_message"),
            rs.getLong("version"),
            instant(rs, "created_at"),
            instant(rs, "updated_at")
        );
    }

    private StepRecord mapStep(ResultSet rs, int rowNum) throws java.sql.SQLException {
        return new StepRecord(
            rs.getLong("id"),
            rs.getLong("checkout_saga_id"),
            CheckoutStepName.valueOf(rs.getString("step_name")),
            CheckoutStepStatus.valueOf(rs.getString("status")),
            CheckoutStepCategory.valueOf(rs.getString("step_category")),
            RecoveryPolicy.valueOf(rs.getString("recovery_policy")),
            rs.getString("idempotency_key"),
            rs.getString("request_payload"),
            rs.getString("response_payload"),
            rs.getInt("retry_count"),
            rs.getInt("max_retry_count"),
            instant(rs, "next_retry_at"),
            rs.getString("error_code"),
            rs.getString("error_message"),
            rs.getString("external_reference_type"),
            rs.getString("external_reference_id"),
            instant(rs, "started_at"),
            instant(rs, "completed_at"),
            instant(rs, "created_at"),
            instant(rs, "updated_at")
        );
    }

    private OutboxEventRecord mapOutboxEvent(ResultSet rs, int rowNum) throws java.sql.SQLException {
        return new OutboxEventRecord(
            rs.getLong("id"),
            rs.getString("aggregate_type"),
            rs.getLong("aggregate_id"),
            rs.getString("event_type"),
            rs.getString("event_key"),
            rs.getString("payload"),
            OutboxStatus.valueOf(rs.getString("status")),
            rs.getInt("retry_count"),
            instant(rs, "next_retry_at"),
            rs.getString("locked_by"),
            instant(rs, "locked_until"),
            rs.getString("error_message"),
            instant(rs, "created_at"),
            instant(rs, "updated_at"),
            instant(rs, "published_at")
        );
    }

    private Timestamp timestamp(Instant value) {
        return value == null ? null : Timestamp.from(value);
    }

    private Instant instant(ResultSet rs, String column) throws java.sql.SQLException {
        Timestamp timestamp = rs.getTimestamp(column);
        return timestamp == null ? null : timestamp.toInstant();
    }
}
