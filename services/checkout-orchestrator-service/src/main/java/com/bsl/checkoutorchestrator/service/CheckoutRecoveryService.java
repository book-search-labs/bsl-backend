package com.bsl.checkoutorchestrator.service;

import com.bsl.checkoutorchestrator.client.CheckoutDownstreamClient;
import com.bsl.checkoutorchestrator.client.DownstreamCallException;
import com.bsl.checkoutorchestrator.common.ApiException;
import com.bsl.checkoutorchestrator.common.ResponseSupport;
import com.bsl.checkoutorchestrator.domain.CheckoutSagaStatus;
import com.bsl.checkoutorchestrator.domain.CheckoutStepName;
import com.bsl.checkoutorchestrator.domain.CheckoutStepStatus;
import com.bsl.checkoutorchestrator.observability.CheckoutSagaMetrics;
import com.bsl.checkoutorchestrator.repository.CheckoutSagaStore;
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
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class CheckoutRecoveryService {
    private static final String SERVICE_NAME = "checkout-orchestrator-service";
    private static final List<CheckoutStepName> COMPENSATION_ORDER = List.of(
        CheckoutStepName.REQUEST_SHIPMENT,
        CheckoutStepName.AUTHORIZE_PAYMENT,
        CheckoutStepName.RESERVE_STOCK
    );

    private final CheckoutSagaStore store;
    private final CheckoutDownstreamClient downstreamClient;
    private final TransactionTemplate transactionTemplate;
    private final ObjectMapper objectMapper;
    private final CheckoutSagaMetrics metrics;
    private final Clock clock;

    public CheckoutRecoveryService(
        CheckoutSagaStore store,
        CheckoutDownstreamClient downstreamClient,
        TransactionTemplate transactionTemplate,
        ObjectMapper objectMapper
    ) {
        this(store, downstreamClient, transactionTemplate, objectMapper, CheckoutSagaMetrics.noop(), Clock.systemUTC());
    }

    @Autowired
    public CheckoutRecoveryService(
        CheckoutSagaStore store,
        CheckoutDownstreamClient downstreamClient,
        TransactionTemplate transactionTemplate,
        ObjectMapper objectMapper,
        CheckoutSagaMetrics metrics
    ) {
        this(store, downstreamClient, transactionTemplate, objectMapper, metrics, Clock.systemUTC());
    }

    CheckoutRecoveryService(
        CheckoutSagaStore store,
        CheckoutDownstreamClient downstreamClient,
        TransactionTemplate transactionTemplate,
        ObjectMapper objectMapper,
        Clock clock
    ) {
        this(store, downstreamClient, transactionTemplate, objectMapper, CheckoutSagaMetrics.noop(), clock);
    }

    CheckoutRecoveryService(
        CheckoutSagaStore store,
        CheckoutDownstreamClient downstreamClient,
        TransactionTemplate transactionTemplate,
        ObjectMapper objectMapper,
        CheckoutSagaMetrics metrics,
        Clock clock
    ) {
        this.store = store;
        this.downstreamClient = downstreamClient;
        this.transactionTemplate = transactionTemplate;
        this.objectMapper = objectMapper;
        this.metrics = metrics;
        this.clock = clock;
    }

    public Map<String, Object> retryStep(
        long checkoutId,
        String stepName,
        Map<String, Object> request,
        String traceId,
        String requestId
    ) {
        String reason = requiredString(request, "reason");
        String operatorId = requiredString(request, "operator_id");
        CheckoutStepName checkoutStepName = parseStepName(stepName);
        return transactionTemplate.execute(status -> {
            SagaRecord saga = findSaga(checkoutId);
            StepRecord step = store.findStepBySagaIdAndName(checkoutId, checkoutStepName)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "checkout_step_not_found", "checkout step을 찾을 수 없습니다."));
            if (step.status() != CheckoutStepStatus.FAILED_RETRYING && step.status() != CheckoutStepStatus.MANUAL_REVIEW_REQUIRED) {
                throw new ApiException(HttpStatus.CONFLICT, "checkout_step_not_retryable", "실패 상태의 step만 manual retry할 수 있습니다.");
            }
            Instant now = clock.instant();
            store.resetStepForManualRetry(step.id(), now);
            store.updateSagaStatus(saga.id(), CheckoutSagaStatus.PROCESSING, checkoutStepName, null, null, now);

            Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
            response.put("checkout_id", checkoutId);
            response.put("step_name", checkoutStepName.name());
            response.put("before_status", step.status().name());
            response.put("after_status", CheckoutStepStatus.READY.name());
            response.put("idempotency_key", step.idempotencyKey());
            response.put("reason", reason);
            response.put("operator_id", operatorId);
            response.put("mode", "db");
            return response;
        });
    }

    public Map<String, Object> reconcileUnknownStep(
        long checkoutId,
        String stepName,
        Map<String, Object> request,
        String traceId,
        String requestId
    ) {
        String reason = requiredString(request, "reason");
        String operatorId = requiredString(request, "operator_id");
        CheckoutStepName checkoutStepName = parseStepName(stepName);
        return transactionTemplate.execute(status -> {
            SagaRecord saga = findSaga(checkoutId);
            StepRecord step = store.findStepBySagaIdAndName(checkoutId, checkoutStepName)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "checkout_step_not_found", "checkout step을 찾을 수 없습니다."));
            if (step.status() != CheckoutStepStatus.UNKNOWN) {
                throw new ApiException(HttpStatus.CONFLICT, "checkout_step_not_unknown", "UNKNOWN 상태의 step만 reconciliation을 예약할 수 있습니다.");
            }
            Instant now = clock.instant();
            store.scheduleUnknownReconciliation(step.id(), now);
            store.updateSagaStatus(saga.id(), CheckoutSagaStatus.PROCESSING, checkoutStepName, null, null, now);

            Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
            response.put("checkout_id", checkoutId);
            response.put("step_name", checkoutStepName.name());
            response.put("before_status", step.status().name());
            response.put("after_status", CheckoutStepStatus.UNKNOWN.name());
            response.put("idempotency_key", step.idempotencyKey());
            response.put("reason", reason);
            response.put("operator_id", operatorId);
            response.put("action", "SCHEDULED_RECONCILIATION");
            response.put("mode", "db");
            return response;
        });
    }

    public Map<String, Object> cancelCheckout(
        long checkoutId,
        Map<String, Object> request,
        String traceId,
        String requestId
    ) {
        String reason = requiredString(request, "reason");
        String operatorId = requiredString(request, "operator_id");
        SagaRecord saga = transactionTemplate.execute(status -> {
            SagaRecord existing = findSaga(checkoutId);
            if (existing.status() == CheckoutSagaStatus.CANCELLED) {
                return existing;
            }
            if (existing.status() != CheckoutSagaStatus.PENDING
                && existing.status() != CheckoutSagaStatus.PROCESSING
                && existing.status() != CheckoutSagaStatus.FAILED_RETRYING
                && existing.status() != CheckoutSagaStatus.MANUAL_REVIEW_REQUIRED
                && existing.status() != CheckoutSagaStatus.SUCCEEDED
                && existing.status() != CheckoutSagaStatus.CANCEL_FAILED) {
                throw new ApiException(HttpStatus.CONFLICT, "checkout_not_cancellable", "현재 checkout 상태에서는 cancel할 수 없습니다.");
            }
            Instant now = clock.instant();
            store.updateSagaStatus(existing.id(), CheckoutSagaStatus.CANCELLING, currentStepName(existing), null, null, now);
            return store.findSagaById(existing.id()).orElse(existing);
        });

        if (saga.status() != CheckoutSagaStatus.CANCELLED) {
            compensateSucceededSteps(saga, reason, operatorId, traceId, requestId);
        }

        SagaRecord latest = findSaga(checkoutId);
        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.put("checkout_id", checkoutId);
        response.put("status", latest.status().name());
        response.put("reason", reason);
        response.put("operator_id", operatorId);
        response.put("mode", "db");
        return response;
    }

    private void compensateSucceededSteps(
        SagaRecord saga,
        String reason,
        String operatorId,
        String traceId,
        String requestId
    ) {
        Map<String, Object> context = readObjectMap(saga.contextPayload());
        for (CheckoutStepName stepName : COMPENSATION_ORDER) {
            StepRecord step = store.findStepBySagaIdAndName(saga.id(), stepName).orElse(null);
            if (step == null || step.status() == CheckoutStepStatus.COMPENSATED) {
                continue;
            }
            if (step.status() != CheckoutStepStatus.SUCCEEDED) {
                continue;
            }

            transactionTemplate.executeWithoutResult(status -> store.markStepCompensating(step.id(), clock.instant()));
            try {
                Map<String, Object> compensationResponse = downstreamClient.compensate(
                    stepName,
                    compensationRequest(saga, stepName, context, reason, operatorId),
                    compensationKey(saga.id(), stepName),
                    traceId,
                    requestId
                );
                transactionTemplate.executeWithoutResult(status -> store.markStepCompensated(
                    step.id(),
                    writeJson(Map.of(
                        "forward_response", readJson(step.responsePayload()),
                        "compensation_response", compensationResponse
                    )),
                    clock.instant()
                ));
                metrics.compensation(stepName, "succeeded");
            } catch (DownstreamCallException ex) {
                metrics.compensation(stepName, "failed");
                transactionTemplate.executeWithoutResult(status -> {
                    Instant now = clock.instant();
                    store.markStepCompensationFailed(step.id(), ex.getCode(), ex.getMessage(), now);
                    store.updateSagaStatus(saga.id(), CheckoutSagaStatus.CANCEL_FAILED, stepName, ex.getCode(), ex.getMessage(), now);
                });
                return;
            }
        }

        transactionTemplate.executeWithoutResult(status -> store.updateSagaStatus(
            saga.id(),
            CheckoutSagaStatus.CANCELLED,
            null,
            null,
            null,
            clock.instant()
        ));
    }

    private Map<String, Object> compensationRequest(
        SagaRecord saga,
        CheckoutStepName stepName,
        Map<String, Object> context,
        String reason,
        String operatorId
    ) {
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("checkout_id", saga.id());
        request.put("reason", reason);
        request.put("operator_id", operatorId);
        switch (stepName) {
            case REQUEST_SHIPMENT -> request.put("shipment_id", required(context, "shipment_request_id"));
            case RESERVE_STOCK -> request.put("reservation_id", required(context, "inventory_reservation_id"));
            case AUTHORIZE_PAYMENT -> request.put("payment_id", required(context, "payment_id"));
            case CREATE_ORDER -> {
            }
        }
        return request;
    }

    private String compensationKey(long checkoutId, CheckoutStepName stepName) {
        return "checkout:" + checkoutId + ":" + stepName.name() + ":compensate";
    }

    private SagaRecord findSaga(long checkoutId) {
        return store.findSagaById(checkoutId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "checkout_not_found", "checkout을 찾을 수 없습니다."));
    }

    private CheckoutStepName parseStepName(String stepName) {
        try {
            return CheckoutStepName.valueOf(stepName);
        } catch (IllegalArgumentException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "지원하지 않는 checkout step입니다.");
        }
    }

    private CheckoutStepName currentStepName(SagaRecord saga) {
        if (saga.currentStep() == null || saga.currentStep().isBlank()) {
            return null;
        }
        try {
            return CheckoutStepName.valueOf(saga.currentStep());
        } catch (IllegalArgumentException ex) {
            return null;
        }
    }

    private String requiredString(Map<String, Object> request, String field) {
        Object value = request == null ? null : request.get(field);
        if (value == null || value.toString().isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + "는 필수입니다.");
        }
        return value.toString();
    }

    private Object required(Map<String, Object> source, String field) {
        Object value = source.get(field);
        if (value == null) {
            throw new ApiException(HttpStatus.CONFLICT, "checkout_context_missing", "보상에 필요한 context가 없습니다: " + field);
        }
        return value;
    }

    private Map<String, Object> readObjectMap(String json) {
        if (json == null || json.isBlank()) {
            return new LinkedHashMap<>();
        }
        try {
            return objectMapper.readValue(json, new TypeReference<>() {
            });
        } catch (JsonProcessingException ex) {
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "checkout_context_invalid", "checkout context를 읽을 수 없습니다.");
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

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "checkout_payload_invalid", "checkout payload를 저장할 수 없습니다.");
        }
    }
}
