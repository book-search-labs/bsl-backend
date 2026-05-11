package com.bsl.checkoutorchestrator.service;

import com.bsl.checkoutorchestrator.common.ApiException;
import com.bsl.checkoutorchestrator.common.ResponseSupport;
import com.bsl.checkoutorchestrator.domain.CheckoutSagaStatus;
import com.bsl.checkoutorchestrator.domain.CheckoutStepCategory;
import com.bsl.checkoutorchestrator.domain.CheckoutStepName;
import com.bsl.checkoutorchestrator.domain.CheckoutStepStatus;
import com.bsl.checkoutorchestrator.domain.OutboxStatus;
import com.bsl.checkoutorchestrator.domain.RecoveryPolicy;
import com.bsl.checkoutorchestrator.observability.CheckoutSagaMetrics;
import com.bsl.checkoutorchestrator.repository.CheckoutSagaStore;
import com.bsl.checkoutorchestrator.repository.NewOutboxEventRecord;
import com.bsl.checkoutorchestrator.repository.NewSagaRecord;
import com.bsl.checkoutorchestrator.repository.NewStepRecord;
import com.bsl.checkoutorchestrator.repository.OutboxEventRecord;
import com.bsl.checkoutorchestrator.repository.SagaRecord;
import com.bsl.checkoutorchestrator.repository.StepRecord;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutSagaService {
    private static final String SERVICE_NAME = "checkout-orchestrator-service";
    private static final String AGGREGATE_TYPE = "CHECKOUT_SAGA";
    private static final String CHECKOUT_STARTED = "CHECKOUT_STARTED";
    private static final List<StepPlan> STEP_PLANS = List.of(
        new StepPlan(CheckoutStepName.CREATE_ORDER, CheckoutStepCategory.COMPENSATABLE, RecoveryPolicy.BACKWARD),
        new StepPlan(CheckoutStepName.RESERVE_STOCK, CheckoutStepCategory.COMPENSATABLE, RecoveryPolicy.BACKWARD),
        new StepPlan(CheckoutStepName.AUTHORIZE_PAYMENT, CheckoutStepCategory.COMPENSATABLE, RecoveryPolicy.BACKWARD),
        new StepPlan(CheckoutStepName.REQUEST_SHIPMENT, CheckoutStepCategory.RETRIABLE, RecoveryPolicy.FORWARD)
    );

    private final CheckoutSagaStore store;
    private final ObjectMapper objectMapper;
    private final CheckoutSagaMetrics metrics;
    private final Clock clock;

    public CheckoutSagaService(CheckoutSagaStore store, ObjectMapper objectMapper) {
        this(store, objectMapper, CheckoutSagaMetrics.noop(), Clock.systemUTC());
    }

    @Autowired
    public CheckoutSagaService(CheckoutSagaStore store, ObjectMapper objectMapper, CheckoutSagaMetrics metrics) {
        this(store, objectMapper, metrics, Clock.systemUTC());
    }

    CheckoutSagaService(CheckoutSagaStore store, ObjectMapper objectMapper, Clock clock) {
        this(store, objectMapper, CheckoutSagaMetrics.noop(), clock);
    }

    CheckoutSagaService(CheckoutSagaStore store, ObjectMapper objectMapper, CheckoutSagaMetrics metrics, Clock clock) {
        this.store = store;
        this.objectMapper = objectMapper;
        this.metrics = metrics;
        this.clock = clock;
    }

    @Transactional
    public Map<String, Object> startCheckout(Map<String, Object> request, String traceId, String requestId) {
        Map<String, Object> requestPayload = normalizeRequest(request);
        String checkoutKey = requiredString(requestPayload, "checkout_key");
        String userId = requiredString(requestPayload, "user_id");
        requirePresent(requestPayload, "items");
        requirePresent(requestPayload, "payment");
        requirePresent(requestPayload, "shipping_address");

        return store.findSagaByCheckoutKey(checkoutKey)
            .map(existing -> toView(existing, traceId, requestId))
            .orElseGet(() -> createNewCheckout(requestPayload, checkoutKey, userId, traceId, requestId));
    }

    @Transactional(readOnly = true)
    public Map<String, Object> listCheckouts(String status, int limit, String traceId, String requestId) {
        CheckoutSagaStatus parsedStatus = parseSagaStatus(status);
        List<SagaRecord> sagas = store.findSagas(parsedStatus, limit);
        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.put("items", sagas.stream().map(this::summaryView).toList());
        response.put("count", sagas.size());
        response.put("status_filter", parsedStatus == null ? null : parsedStatus.name());
        response.put("limit", Math.max(1, Math.min(limit, 200)));
        response.put("mode", "db");
        return response;
    }

    @Transactional(readOnly = true)
    public Map<String, Object> getCheckout(long checkoutId, String traceId, String requestId) {
        SagaRecord saga = store.findSagaById(checkoutId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "checkout_not_found", "checkout을 찾을 수 없습니다."));
        return toView(saga, traceId, requestId);
    }

    private Map<String, Object> createNewCheckout(
        Map<String, Object> requestPayload,
        String checkoutKey,
        String userId,
        String traceId,
        String requestId
    ) {
        Instant now = clock.instant();
        String requestJson = writeJson(requestPayload);
        String contextJson = writeJson(Map.of());
        long sagaId;
        try {
            sagaId = store.insertSaga(new NewSagaRecord(
                checkoutKey,
                userId,
                CheckoutSagaStatus.PENDING,
                null,
                requestJson,
                contextJson,
                null,
                null,
                0L,
                now,
                now
            ));
        } catch (DuplicateKeyException ex) {
            SagaRecord existing = store.findSagaByCheckoutKey(checkoutKey)
                .orElseThrow(() -> ex);
            return toView(existing, traceId, requestId);
        }

        for (StepPlan plan : STEP_PLANS) {
            store.insertStep(new NewStepRecord(
                sagaId,
                plan.stepName(),
                CheckoutStepStatus.READY,
                plan.stepCategory(),
                plan.recoveryPolicy(),
                idempotencyKey(sagaId, plan.stepName()),
                requestJson,
                null,
                0,
                5,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                now,
                now
            ));
        }

        store.insertOutboxEvent(new NewOutboxEventRecord(
            AGGREGATE_TYPE,
            sagaId,
            CHECKOUT_STARTED,
            "checkout:" + sagaId + ":" + CHECKOUT_STARTED + ":v1",
            writeJson(checkoutStartedPayload(sagaId, checkoutKey, userId, traceId, requestId, now)),
            OutboxStatus.READY,
            0,
            null,
            null,
            null,
            null,
            now,
            now,
            null
        ));
        metrics.started();

        SagaRecord saga = store.findSagaById(sagaId)
            .orElseThrow(() -> new IllegalStateException("created checkout_saga is missing: " + sagaId));
        return toView(saga, traceId, requestId);
    }

    private Map<String, Object> toView(SagaRecord saga, String traceId, String requestId) {
        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.put("checkout_id", saga.id());
        response.put("checkout_key", saga.checkoutKey());
        response.put("user_id", saga.userId());
        response.put("status", saga.status().name());
        response.put("current_step", saga.currentStep());
        response.put("request_payload", readJson(saga.requestPayload()));
        response.put("context_payload", readJson(saga.contextPayload()));
        response.put("error_code", saga.errorCode());
        response.put("error_message", saga.errorMessage());
        response.put("saga_version", saga.version());
        response.put("created_at", iso(saga.createdAt()));
        response.put("updated_at", iso(saga.updatedAt()));
        response.put("steps", store.findStepsBySagaId(saga.id()).stream().map(this::stepView).toList());
        response.put("outbox_events", store.findOutboxEventsByAggregate(AGGREGATE_TYPE, saga.id()).stream()
            .map(this::outboxView)
            .toList());
        response.put("mode", "db");
        return response;
    }

    private Map<String, Object> summaryView(SagaRecord saga) {
        List<StepRecord> steps = store.findStepsBySagaId(saga.id());
        List<OutboxEventRecord> outboxEvents = store.findOutboxEventsByAggregate(AGGREGATE_TYPE, saga.id());
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("checkout_id", saga.id());
        view.put("checkout_key", saga.checkoutKey());
        view.put("user_id", saga.userId());
        view.put("status", saga.status().name());
        view.put("current_step", saga.currentStep());
        view.put("error_code", saga.errorCode());
        view.put("error_message", saga.errorMessage());
        view.put("saga_version", saga.version());
        view.put("created_at", iso(saga.createdAt()));
        view.put("updated_at", iso(saga.updatedAt()));
        view.put("steps", steps.stream().map(this::stepSummaryView).toList());
        view.put("failed_steps", steps.stream()
            .filter(step -> step.status() == CheckoutStepStatus.FAILED_RETRYING
                || step.status() == CheckoutStepStatus.MANUAL_REVIEW_REQUIRED
                || step.status() == CheckoutStepStatus.UNKNOWN)
            .map(this::stepSummaryView)
            .toList());
        view.put("outbox_event_count", outboxEvents.size());
        return view;
    }

    private Map<String, Object> stepSummaryView(StepRecord step) {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("step_name", step.stepName().name());
        view.put("status", step.status().name());
        view.put("step_category", step.stepCategory().name());
        view.put("recovery_policy", step.recoveryPolicy().name());
        view.put("retry_count", step.retryCount());
        view.put("max_retry_count", step.maxRetryCount());
        view.put("next_retry_at", iso(step.nextRetryAt()));
        view.put("error_code", step.errorCode());
        view.put("error_message", step.errorMessage());
        return view;
    }

    private Map<String, Object> stepView(StepRecord step) {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("step_name", step.stepName().name());
        view.put("status", step.status().name());
        view.put("step_category", step.stepCategory().name());
        view.put("recovery_policy", step.recoveryPolicy().name());
        view.put("idempotency_key", step.idempotencyKey());
        view.put("request_payload", readJson(step.requestPayload()));
        view.put("response_payload", readJson(step.responsePayload()));
        view.put("retry_count", step.retryCount());
        view.put("max_retry_count", step.maxRetryCount());
        view.put("next_retry_at", iso(step.nextRetryAt()));
        view.put("error_code", step.errorCode());
        view.put("error_message", step.errorMessage());
        view.put("external_reference_type", step.externalReferenceType());
        view.put("external_reference_id", step.externalReferenceId());
        view.put("started_at", iso(step.startedAt()));
        view.put("completed_at", iso(step.completedAt()));
        view.put("created_at", iso(step.createdAt()));
        view.put("updated_at", iso(step.updatedAt()));
        return view;
    }

    private CheckoutSagaStatus parseSagaStatus(String status) {
        if (status == null || status.isBlank()) {
            return null;
        }
        try {
            return CheckoutSagaStatus.valueOf(status.trim().toUpperCase());
        } catch (IllegalArgumentException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "지원하지 않는 checkout saga status입니다.");
        }
    }

    private Map<String, Object> outboxView(OutboxEventRecord event) {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("event_type", event.eventType());
        view.put("event_key", event.eventKey());
        view.put("status", event.status().name());
        view.put("payload", readJson(event.payload()));
        view.put("retry_count", event.retryCount());
        view.put("created_at", iso(event.createdAt()));
        view.put("updated_at", iso(event.updatedAt()));
        view.put("published_at", iso(event.publishedAt()));
        return view;
    }

    private Map<String, Object> checkoutStartedPayload(
        long checkoutId,
        String checkoutKey,
        String userId,
        String traceId,
        String requestId,
        Instant occurredAt
    ) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("event_version", "v1");
        payload.put("checkout_id", checkoutId);
        payload.put("checkout_key", checkoutKey);
        payload.put("user_id", userId);
        payload.put("status", CheckoutSagaStatus.PENDING.name());
        payload.put("current_step", null);
        payload.put("trace_id", traceId == null || traceId.isBlank() ? "unknown" : traceId);
        payload.put("request_id", requestId == null || requestId.isBlank() ? "unknown" : requestId);
        payload.put("occurred_at", occurredAt.toString());
        return payload;
    }

    private Map<String, Object> normalizeRequest(Map<String, Object> request) {
        if (request == null) {
            return Map.of();
        }
        return new LinkedHashMap<>(request);
    }

    private String requiredString(Map<String, Object> request, String field) {
        Object value = request.get(field);
        if (value == null || value.toString().isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + "는 필수입니다.");
        }
        return value.toString();
    }

    private void requirePresent(Map<String, Object> request, String field) {
        Object value = request.get(field);
        if (value == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + "는 필수입니다.");
        }
    }

    private String idempotencyKey(long checkoutId, CheckoutStepName stepName) {
        return "checkout:" + checkoutId + ":" + stepName.name();
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "요청 payload를 JSON으로 직렬화할 수 없습니다.");
        }
    }

    private Object readJson(String json) {
        if (json == null || json.isBlank()) {
            return null;
        }
        try {
            return objectMapper.readValue(json, new TypeReference<>() {
            });
        } catch (JsonProcessingException ex) {
            return json;
        }
    }

    private String iso(Instant instant) {
        return instant == null ? null : instant.toString();
    }

    private record StepPlan(
        CheckoutStepName stepName,
        CheckoutStepCategory stepCategory,
        RecoveryPolicy recoveryPolicy
    ) {
    }
}
