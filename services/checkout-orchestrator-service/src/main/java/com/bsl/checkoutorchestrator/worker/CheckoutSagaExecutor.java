package com.bsl.checkoutorchestrator.worker;

import com.bsl.checkoutorchestrator.client.CheckoutDownstreamClient;
import com.bsl.checkoutorchestrator.client.DownstreamCallException;
import com.bsl.checkoutorchestrator.config.CheckoutOrchestratorProperties;
import com.bsl.checkoutorchestrator.domain.CheckoutSagaStatus;
import com.bsl.checkoutorchestrator.domain.CheckoutStepName;
import com.bsl.checkoutorchestrator.domain.CheckoutStepStatus;
import com.bsl.checkoutorchestrator.domain.OutboxStatus;
import com.bsl.checkoutorchestrator.observability.CheckoutSagaMetrics;
import com.bsl.checkoutorchestrator.repository.CheckoutSagaStore;
import com.bsl.checkoutorchestrator.repository.NewOutboxEventRecord;
import com.bsl.checkoutorchestrator.repository.SagaRecord;
import com.bsl.checkoutorchestrator.repository.StepRecord;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class CheckoutSagaExecutor {
    private static final String AGGREGATE_TYPE = "CHECKOUT_SAGA";
    private static final String CHECKOUT_COMPLETED = "CHECKOUT_COMPLETED";
    private static final List<CheckoutStepName> STEP_ORDER = List.of(
        CheckoutStepName.CREATE_ORDER,
        CheckoutStepName.RESERVE_STOCK,
        CheckoutStepName.AUTHORIZE_PAYMENT,
        CheckoutStepName.REQUEST_SHIPMENT
    );

    private final CheckoutSagaStore store;
    private final CheckoutDownstreamClient downstreamClient;
    private final CheckoutOrchestratorProperties properties;
    private final TransactionTemplate transactionTemplate;
    private final ObjectMapper objectMapper;
    private final CheckoutSagaMetrics metrics;
    private final Clock clock;

    public CheckoutSagaExecutor(
        CheckoutSagaStore store,
        CheckoutDownstreamClient downstreamClient,
        CheckoutOrchestratorProperties properties,
        TransactionTemplate transactionTemplate,
        ObjectMapper objectMapper
    ) {
        this(store, downstreamClient, properties, transactionTemplate, objectMapper, CheckoutSagaMetrics.noop(), Clock.systemUTC());
    }

    @Autowired
    public CheckoutSagaExecutor(
        CheckoutSagaStore store,
        CheckoutDownstreamClient downstreamClient,
        CheckoutOrchestratorProperties properties,
        TransactionTemplate transactionTemplate,
        ObjectMapper objectMapper,
        CheckoutSagaMetrics metrics
    ) {
        this(store, downstreamClient, properties, transactionTemplate, objectMapper, metrics, Clock.systemUTC());
    }

    CheckoutSagaExecutor(
        CheckoutSagaStore store,
        CheckoutDownstreamClient downstreamClient,
        CheckoutOrchestratorProperties properties,
        TransactionTemplate transactionTemplate,
        ObjectMapper objectMapper,
        Clock clock
    ) {
        this(store, downstreamClient, properties, transactionTemplate, objectMapper, CheckoutSagaMetrics.noop(), clock);
    }

    CheckoutSagaExecutor(
        CheckoutSagaStore store,
        CheckoutDownstreamClient downstreamClient,
        CheckoutOrchestratorProperties properties,
        TransactionTemplate transactionTemplate,
        ObjectMapper objectMapper,
        CheckoutSagaMetrics metrics,
        Clock clock
    ) {
        this.store = store;
        this.downstreamClient = downstreamClient;
        this.properties = properties;
        this.transactionTemplate = transactionTemplate;
        this.objectMapper = objectMapper;
        this.metrics = metrics;
        this.clock = clock;
    }

    public int executeDueSteps(int maxSteps, String traceId, String requestId) {
        int executed = 0;
        for (int i = 0; i < maxSteps; i++) {
            ClaimedStep claimed = transactionTemplate.execute(status -> claimNextDueStep());
            if (claimed == null) {
                break;
            }
            executeClaimedStep(claimed, traceId, requestId);
            executed++;
        }
        return executed;
    }

    private ClaimedStep claimNextDueStep() {
        Instant now = clock.instant();
        List<StepRecord> candidates = store.findDueSteps(now, properties.getWorker().getBatchSize());
        for (StepRecord candidate : candidates) {
            SagaRecord saga = store.findSagaById(candidate.checkoutSagaId()).orElse(null);
            if (saga == null) {
                continue;
            }
            List<StepRecord> steps = store.findStepsBySagaId(candidate.checkoutSagaId());
            if (!isExecutable(candidate, steps)) {
                continue;
            }
            if (store.claimStepForProcessing(candidate.id(), candidate.status(), now) != 1) {
                continue;
            }
            store.updateSagaStatus(saga.id(), CheckoutSagaStatus.PROCESSING, candidate.stepName(), null, null, now);
            return new ClaimedStep(saga, candidate, candidate.status());
        }
        return null;
    }

    private boolean isExecutable(StepRecord candidate, List<StepRecord> steps) {
        int candidateIndex = STEP_ORDER.indexOf(candidate.stepName());
        if (candidateIndex < 0) {
            return false;
        }
        for (int i = 0; i < candidateIndex; i++) {
            CheckoutStepName previousStepName = STEP_ORDER.get(i);
            StepRecord previous = findStep(steps, previousStepName);
            if (previous == null || previous.status() != CheckoutStepStatus.SUCCEEDED) {
                return false;
            }
        }
        return true;
    }

    private void executeClaimedStep(ClaimedStep claimed, String traceId, String requestId) {
        try {
            Map<String, Object> response = claimed.originalStatus() == CheckoutStepStatus.UNKNOWN
                ? reconcileUnknownStep(claimed, traceId, requestId)
                : downstreamClient.execute(
                    claimed.step().stepName(),
                    buildDownstreamRequest(claimed.saga(), claimed.step()),
                    claimed.step().idempotencyKey(),
                    traceId,
                    requestId
                );
            transactionTemplate.executeWithoutResult(status -> completeStepSucceeded(claimed, response, traceId, requestId));
        } catch (DownstreamCallException ex) {
            transactionTemplate.executeWithoutResult(status -> completeStepFailed(claimed, ex));
        } catch (RuntimeException ex) {
            transactionTemplate.executeWithoutResult(status -> completeStepFailed(
                claimed,
                new DownstreamCallException("step_execution_failed", ex.getMessage(), false, true)
            ));
        }
    }

    private Map<String, Object> reconcileUnknownStep(ClaimedStep claimed, String traceId, String requestId) {
        Optional<Map<String, Object>> reconciled = downstreamClient.reconcile(
                claimed.step().stepName(),
                claimed.step().idempotencyKey(),
                traceId,
                requestId
            );
        if (reconciled.isPresent()) {
            metrics.reconciliation(claimed.step().stepName(), "succeeded");
            return reconciled.get();
        }
        metrics.reconciliation(claimed.step().stepName(), "pending");
        throw new DownstreamCallException(
                "unknown_reconciliation_pending",
                "downstream result is still unknown: " + claimed.step().stepName(),
                false,
                true
            );
    }

    private void completeStepSucceeded(ClaimedStep claimed, Map<String, Object> response, String traceId, String requestId) {
        Instant now = clock.instant();
        SagaRecord saga = store.findSagaById(claimed.saga().id()).orElse(claimed.saga());
        Map<String, Object> context = readObjectMap(saga.contextPayload());
        mergeContext(context, claimed.step().stepName(), response);

        store.markStepSucceeded(claimed.step().id(), writeJson(response), now);
        store.updateSagaContext(saga.id(), writeJson(context), now);

        List<StepRecord> steps = store.findStepsBySagaId(saga.id());
        boolean allSucceeded = steps.stream().allMatch(step -> step.status() == CheckoutStepStatus.SUCCEEDED);
        if (allSucceeded) {
            store.updateSagaStatus(saga.id(), CheckoutSagaStatus.SUCCEEDED, null, null, null, now);
            insertCheckoutCompletedEvent(saga, context, traceId, requestId, now);
            metrics.completed();
        }
    }

    private void completeStepFailed(ClaimedStep claimed, DownstreamCallException ex) {
        Instant now = clock.instant();
        int retryCount = claimed.step().retryCount() + 1;
        if (!ex.isRetryable() || retryCount >= claimed.step().maxRetryCount()) {
            recordFailureMetric(claimed.step().stepName(), ex);
            metrics.manualReview(claimed.step().stepName(), ex.getCode());
            if (claimed.step().recoveryPolicy().name().equals("FORWARD")) {
                metrics.pivotManualReview(claimed.step().stepName(), ex.getCode());
            }
            store.markStepManualReview(claimed.step().id(), ex.getCode(), ex.getMessage(), now);
            store.updateSagaStatus(
                claimed.saga().id(),
                CheckoutSagaStatus.MANUAL_REVIEW_REQUIRED,
                claimed.step().stepName(),
                ex.getCode(),
                ex.getMessage(),
                now
            );
            return;
        }

        Instant nextRetryAt = now.plusMillis(properties.getWorker().getRetryDelayMs());
        if (ex.isUnknownOutcome()) {
            metrics.unknown(claimed.step().stepName(), ex.getCode());
            store.markStepUnknown(claimed.step().id(), retryCount, nextRetryAt, ex.getCode(), ex.getMessage(), now);
        } else {
            metrics.failed(claimed.step().stepName(), ex.getCode());
            store.markStepFailedRetrying(claimed.step().id(), retryCount, nextRetryAt, ex.getCode(), ex.getMessage(), now);
        }
        store.updateSagaStatus(
            claimed.saga().id(),
            CheckoutSagaStatus.FAILED_RETRYING,
            claimed.step().stepName(),
            ex.getCode(),
            ex.getMessage(),
            now
        );
    }

    private void recordFailureMetric(CheckoutStepName stepName, DownstreamCallException ex) {
        if (ex.isUnknownOutcome()) {
            metrics.unknown(stepName, ex.getCode());
        } else {
            metrics.failed(stepName, ex.getCode());
        }
    }

    private void insertCheckoutCompletedEvent(
        SagaRecord saga,
        Map<String, Object> context,
        String traceId,
        String requestId,
        Instant now
    ) {
        String eventKey = "checkout:" + saga.id() + ":" + CHECKOUT_COMPLETED + ":v1";
        if (store.outboxEventExists(eventKey)) {
            return;
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("event_version", "v1");
        payload.put("checkout_id", saga.id());
        payload.put("checkout_key", saga.checkoutKey());
        payload.put("user_id", saga.userId());
        payload.put("status", CheckoutSagaStatus.SUCCEEDED.name());
        payload.put("current_step", null);
        payload.put("context_payload", context);
        payload.put("trace_id", traceId == null || traceId.isBlank() ? "worker" : traceId);
        payload.put("request_id", requestId == null || requestId.isBlank() ? "worker" : requestId);
        payload.put("occurred_at", now.toString());

        store.insertOutboxEvent(new NewOutboxEventRecord(
            AGGREGATE_TYPE,
            saga.id(),
            CHECKOUT_COMPLETED,
            eventKey,
            writeJson(payload),
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
    }

    private Map<String, Object> buildDownstreamRequest(SagaRecord saga, StepRecord step) {
        Map<String, Object> requestPayload = readObjectMap(saga.requestPayload());
        Map<String, Object> context = readObjectMap(saga.contextPayload());
        return switch (step.stepName()) {
            case CREATE_ORDER -> orderRequest(saga, requestPayload);
            case RESERVE_STOCK -> inventoryReserveRequest(saga, requestPayload, context);
            case AUTHORIZE_PAYMENT -> paymentAuthorizeRequest(saga, requestPayload, context);
            case REQUEST_SHIPMENT -> shipmentRequest(saga, requestPayload, context);
        };
    }

    private Map<String, Object> orderRequest(SagaRecord saga, Map<String, Object> requestPayload) {
        Map<String, Object> payment = objectMap(requestPayload.get("payment"));
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("checkout_id", saga.id());
        request.put("user_id", saga.userId());
        request.put("items", required(requestPayload, "items"));
        request.put("total_amount", payment.getOrDefault("amount", requestPayload.get("total_amount")));
        request.put("currency", payment.getOrDefault("currency", requestPayload.getOrDefault("currency", "KRW")));
        return request;
    }

    private Map<String, Object> inventoryReserveRequest(
        SagaRecord saga,
        Map<String, Object> requestPayload,
        Map<String, Object> context
    ) {
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("checkout_id", saga.id());
        request.put("order_id", required(context, "order_id"));
        request.put("items", required(requestPayload, "items"));
        return request;
    }

    private Map<String, Object> paymentAuthorizeRequest(
        SagaRecord saga,
        Map<String, Object> requestPayload,
        Map<String, Object> context
    ) {
        Map<String, Object> payment = objectMap(requestPayload.get("payment"));
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("checkout_id", saga.id());
        request.put("order_id", required(context, "order_id"));
        request.put("amount", required(payment, "amount"));
        request.put("currency", payment.getOrDefault("currency", "KRW"));
        request.put("method", payment.getOrDefault("method", "MOCK"));
        return request;
    }

    private Map<String, Object> shipmentRequest(
        SagaRecord saga,
        Map<String, Object> requestPayload,
        Map<String, Object> context
    ) {
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("checkout_id", saga.id());
        request.put("order_id", required(context, "order_id"));
        request.put("shipping_address", required(requestPayload, "shipping_address"));
        request.put("items", required(requestPayload, "items"));
        return request;
    }

    private void mergeContext(Map<String, Object> context, CheckoutStepName stepName, Map<String, Object> response) {
        switch (stepName) {
            case CREATE_ORDER -> putIfPresent(context, "order_id", response.get("order_id"));
            case RESERVE_STOCK -> putIfPresent(context, "inventory_reservation_id", response.get("reservation_id"));
            case AUTHORIZE_PAYMENT -> {
                putIfPresent(context, "payment_id", response.get("payment_id"));
                putIfPresent(context, "pg_transaction_id", response.get("pg_transaction_id"));
            }
            case REQUEST_SHIPMENT -> putIfPresent(context, "shipment_request_id", response.get("shipment_id"));
        }
    }

    private StepRecord findStep(List<StepRecord> steps, CheckoutStepName stepName) {
        return steps.stream()
            .filter(step -> step.stepName() == stepName)
            .findFirst()
            .orElse(null);
    }

    private Object required(Map<String, Object> source, String field) {
        Object value = source.get(field);
        if (value == null) {
            throw new DownstreamCallException("invalid_step_request", field + " is required", false, false);
        }
        return value;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> objectMap(Object value) {
        if (value instanceof Map<?, ?> map) {
            return new LinkedHashMap<>((Map<String, Object>) map);
        }
        return new LinkedHashMap<>();
    }

    private void putIfPresent(Map<String, Object> target, String key, Object value) {
        if (value != null) {
            target.put(key, value);
        }
    }

    private Map<String, Object> readObjectMap(String json) {
        if (json == null || json.isBlank()) {
            return new LinkedHashMap<>();
        }
        try {
            return objectMapper.readValue(json, new TypeReference<>() {
            });
        } catch (JsonProcessingException ex) {
            throw new DownstreamCallException("invalid_saga_json", "saga JSON payload is invalid", false, false);
        }
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new DownstreamCallException("invalid_saga_json", "saga JSON payload cannot be serialized", false, false);
        }
    }

    private record ClaimedStep(
        SagaRecord saga,
        StepRecord step,
        CheckoutStepStatus originalStatus
    ) {
    }
}
