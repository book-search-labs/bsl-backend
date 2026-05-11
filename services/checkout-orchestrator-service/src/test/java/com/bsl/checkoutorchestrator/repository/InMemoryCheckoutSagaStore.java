package com.bsl.checkoutorchestrator.repository;

import com.bsl.checkoutorchestrator.domain.CheckoutSagaStatus;
import com.bsl.checkoutorchestrator.domain.CheckoutStepName;
import com.bsl.checkoutorchestrator.domain.CheckoutStepStatus;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;

public class InMemoryCheckoutSagaStore implements CheckoutSagaStore {
    private final AtomicLong sagaSequence = new AtomicLong(1L);
    private final AtomicLong stepSequence = new AtomicLong(1L);
    private final AtomicLong outboxSequence = new AtomicLong(1L);
    private final Map<Long, SagaRecord> sagas = new LinkedHashMap<>();
    private final Map<Long, List<StepRecord>> steps = new LinkedHashMap<>();
    private final List<OutboxEventRecord> outboxEvents = new ArrayList<>();

    @Override
    public Optional<SagaRecord> findSagaByCheckoutKey(String checkoutKey) {
        return sagas.values().stream()
            .filter(saga -> saga.checkoutKey().equals(checkoutKey))
            .findFirst();
    }

    @Override
    public Optional<SagaRecord> findSagaById(long checkoutId) {
        return Optional.ofNullable(sagas.get(checkoutId));
    }

    @Override
    public List<SagaRecord> findSagas(CheckoutSagaStatus status, int limit) {
        return sagas.values().stream()
            .filter(saga -> status == null || saga.status() == status)
            .sorted((left, right) -> {
                int updated = right.updatedAt().compareTo(left.updatedAt());
                return updated == 0 ? Long.compare(right.id(), left.id()) : updated;
            })
            .limit(Math.max(1, Math.min(limit, 200)))
            .toList();
    }

    @Override
    public List<StepRecord> findStepsBySagaId(long checkoutSagaId) {
        return List.copyOf(steps.getOrDefault(checkoutSagaId, List.of()));
    }

    @Override
    public List<OutboxEventRecord> findOutboxEventsByAggregate(String aggregateType, long aggregateId) {
        return outboxEvents.stream()
            .filter(event -> event.aggregateType().equals(aggregateType) && event.aggregateId() == aggregateId)
            .toList();
    }

    @Override
    public List<StepRecord> findDueSteps(Instant now, int limit) {
        return steps.values().stream()
            .flatMap(List::stream)
            .filter(step -> step.status() == CheckoutStepStatus.READY
                || step.status() == CheckoutStepStatus.FAILED_RETRYING
                || step.status() == CheckoutStepStatus.UNKNOWN)
            .filter(step -> step.nextRetryAt() == null || !step.nextRetryAt().isAfter(now))
            .filter(step -> {
                SagaRecord saga = sagas.get(step.checkoutSagaId());
                return saga != null
                    && (saga.status() == CheckoutSagaStatus.PENDING
                    || saga.status() == CheckoutSagaStatus.PROCESSING
                    || saga.status() == CheckoutSagaStatus.FAILED_RETRYING);
            })
            .limit(limit)
            .toList();
    }

    @Override
    public Optional<StepRecord> findStepById(long stepId) {
        return steps.values().stream()
            .flatMap(List::stream)
            .filter(step -> step.id() == stepId)
            .findFirst();
    }

    @Override
    public Optional<StepRecord> findStepBySagaIdAndName(long checkoutSagaId, CheckoutStepName stepName) {
        return steps.getOrDefault(checkoutSagaId, List.of()).stream()
            .filter(step -> step.stepName() == stepName)
            .findFirst();
    }

    @Override
    public long insertSaga(NewSagaRecord saga) {
        long id = sagaSequence.getAndIncrement();
        sagas.put(id, new SagaRecord(
            id,
            saga.checkoutKey(),
            saga.userId(),
            saga.status(),
            saga.currentStep(),
            saga.requestPayload(),
            saga.contextPayload(),
            saga.errorCode(),
            saga.errorMessage(),
            saga.version(),
            saga.createdAt(),
            saga.updatedAt()
        ));
        return id;
    }

    @Override
    public void insertStep(NewStepRecord step) {
        long id = stepSequence.getAndIncrement();
        steps.computeIfAbsent(step.checkoutSagaId(), ignored -> new ArrayList<>()).add(new StepRecord(
            id,
            step.checkoutSagaId(),
            step.stepName(),
            step.status(),
            step.stepCategory(),
            step.recoveryPolicy(),
            step.idempotencyKey(),
            step.requestPayload(),
            step.responsePayload(),
            step.retryCount(),
            step.maxRetryCount(),
            step.nextRetryAt(),
            step.errorCode(),
            step.errorMessage(),
            step.externalReferenceType(),
            step.externalReferenceId(),
            step.startedAt(),
            step.completedAt(),
            step.createdAt(),
            step.updatedAt()
        ));
    }

    @Override
    public void insertOutboxEvent(NewOutboxEventRecord event) {
        long id = outboxSequence.getAndIncrement();
        outboxEvents.add(new OutboxEventRecord(
            id,
            event.aggregateType(),
            event.aggregateId(),
            event.eventType(),
            event.eventKey(),
            event.payload(),
            event.status(),
            event.retryCount(),
            event.nextRetryAt(),
            event.lockedBy(),
            event.lockedUntil(),
            event.errorMessage(),
            event.createdAt(),
            event.updatedAt(),
            event.publishedAt()
        ));
    }

    @Override
    public boolean outboxEventExists(String eventKey) {
        return outboxEvents.stream().anyMatch(event -> event.eventKey().equals(eventKey));
    }

    @Override
    public int claimStepForProcessing(long stepId, CheckoutStepStatus expectedStatus, Instant now) {
        StepRecord step = findStepById(stepId).orElse(null);
        if (step == null || step.status() != expectedStatus || (step.nextRetryAt() != null && step.nextRetryAt().isAfter(now))) {
            return 0;
        }
        replaceStep(step, new StepRecord(
            step.id(),
            step.checkoutSagaId(),
            step.stepName(),
            CheckoutStepStatus.PROCESSING,
            step.stepCategory(),
            step.recoveryPolicy(),
            step.idempotencyKey(),
            step.requestPayload(),
            step.responsePayload(),
            step.retryCount(),
            step.maxRetryCount(),
            step.nextRetryAt(),
            step.errorCode(),
            step.errorMessage(),
            step.externalReferenceType(),
            step.externalReferenceId(),
            step.startedAt() == null ? now : step.startedAt(),
            step.completedAt(),
            step.createdAt(),
            now
        ));
        return 1;
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
        SagaRecord saga = sagas.get(sagaId);
        sagas.put(sagaId, new SagaRecord(
            saga.id(),
            saga.checkoutKey(),
            saga.userId(),
            status,
            currentStep == null ? null : currentStep.name(),
            saga.requestPayload(),
            saga.contextPayload(),
            errorCode,
            errorMessage,
            saga.version() + 1,
            saga.createdAt(),
            now
        ));
    }

    @Override
    public void updateSagaContext(long sagaId, String contextPayload, Instant now) {
        SagaRecord saga = sagas.get(sagaId);
        sagas.put(sagaId, new SagaRecord(
            saga.id(),
            saga.checkoutKey(),
            saga.userId(),
            saga.status(),
            saga.currentStep(),
            saga.requestPayload(),
            contextPayload,
            saga.errorCode(),
            saga.errorMessage(),
            saga.version() + 1,
            saga.createdAt(),
            now
        ));
    }

    @Override
    public void markStepSucceeded(long stepId, String responsePayload, Instant now) {
        StepRecord step = findStepById(stepId).orElseThrow();
        replaceStep(step, new StepRecord(
            step.id(),
            step.checkoutSagaId(),
            step.stepName(),
            CheckoutStepStatus.SUCCEEDED,
            step.stepCategory(),
            step.recoveryPolicy(),
            step.idempotencyKey(),
            step.requestPayload(),
            responsePayload,
            step.retryCount(),
            step.maxRetryCount(),
            null,
            null,
            null,
            step.externalReferenceType(),
            step.externalReferenceId(),
            step.startedAt(),
            now,
            step.createdAt(),
            now
        ));
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
        StepRecord step = findStepById(stepId).orElseThrow();
        replaceStep(step, new StepRecord(
            step.id(),
            step.checkoutSagaId(),
            step.stepName(),
            CheckoutStepStatus.FAILED_RETRYING,
            step.stepCategory(),
            step.recoveryPolicy(),
            step.idempotencyKey(),
            step.requestPayload(),
            step.responsePayload(),
            retryCount,
            step.maxRetryCount(),
            nextRetryAt,
            errorCode,
            errorMessage,
            step.externalReferenceType(),
            step.externalReferenceId(),
            step.startedAt(),
            step.completedAt(),
            step.createdAt(),
            now
        ));
    }

    @Override
    public void markStepUnknown(long stepId, int retryCount, Instant nextRetryAt, String errorCode, String errorMessage, Instant now) {
        StepRecord step = findStepById(stepId).orElseThrow();
        replaceStep(step, new StepRecord(
            step.id(),
            step.checkoutSagaId(),
            step.stepName(),
            CheckoutStepStatus.UNKNOWN,
            step.stepCategory(),
            step.recoveryPolicy(),
            step.idempotencyKey(),
            step.requestPayload(),
            step.responsePayload(),
            retryCount,
            step.maxRetryCount(),
            nextRetryAt,
            errorCode,
            errorMessage,
            step.externalReferenceType(),
            step.externalReferenceId(),
            step.startedAt(),
            step.completedAt(),
            step.createdAt(),
            now
        ));
    }

    @Override
    public void markStepManualReview(long stepId, String errorCode, String errorMessage, Instant now) {
        StepRecord step = findStepById(stepId).orElseThrow();
        replaceStep(step, new StepRecord(
            step.id(),
            step.checkoutSagaId(),
            step.stepName(),
            CheckoutStepStatus.MANUAL_REVIEW_REQUIRED,
            step.stepCategory(),
            step.recoveryPolicy(),
            step.idempotencyKey(),
            step.requestPayload(),
            step.responsePayload(),
            step.retryCount(),
            step.maxRetryCount(),
            null,
            errorCode,
            errorMessage,
            step.externalReferenceType(),
            step.externalReferenceId(),
            step.startedAt(),
            step.completedAt(),
            step.createdAt(),
            now
        ));
    }

    @Override
    public void resetStepForManualRetry(long stepId, Instant now) {
        StepRecord step = findStepById(stepId).orElseThrow();
        if (step.status() != CheckoutStepStatus.FAILED_RETRYING && step.status() != CheckoutStepStatus.MANUAL_REVIEW_REQUIRED) {
            return;
        }
        replaceStep(step, new StepRecord(
            step.id(),
            step.checkoutSagaId(),
            step.stepName(),
            CheckoutStepStatus.READY,
            step.stepCategory(),
            step.recoveryPolicy(),
            step.idempotencyKey(),
            step.requestPayload(),
            step.responsePayload(),
            step.retryCount(),
            step.maxRetryCount(),
            null,
            null,
            null,
            step.externalReferenceType(),
            step.externalReferenceId(),
            step.startedAt(),
            step.completedAt(),
            step.createdAt(),
            now
        ));
    }

    @Override
    public void scheduleUnknownReconciliation(long stepId, Instant now) {
        StepRecord step = findStepById(stepId).orElseThrow();
        if (step.status() != CheckoutStepStatus.UNKNOWN) {
            return;
        }
        replaceStep(step, new StepRecord(
            step.id(),
            step.checkoutSagaId(),
            step.stepName(),
            CheckoutStepStatus.UNKNOWN,
            step.stepCategory(),
            step.recoveryPolicy(),
            step.idempotencyKey(),
            step.requestPayload(),
            step.responsePayload(),
            step.retryCount(),
            step.maxRetryCount(),
            null,
            step.errorCode(),
            step.errorMessage(),
            step.externalReferenceType(),
            step.externalReferenceId(),
            step.startedAt(),
            step.completedAt(),
            step.createdAt(),
            now
        ));
    }

    @Override
    public void markStepCompensating(long stepId, Instant now) {
        StepRecord step = findStepById(stepId).orElseThrow();
        replaceStep(step, new StepRecord(
            step.id(),
            step.checkoutSagaId(),
            step.stepName(),
            CheckoutStepStatus.COMPENSATING,
            step.stepCategory(),
            step.recoveryPolicy(),
            step.idempotencyKey(),
            step.requestPayload(),
            step.responsePayload(),
            step.retryCount(),
            step.maxRetryCount(),
            step.nextRetryAt(),
            step.errorCode(),
            step.errorMessage(),
            step.externalReferenceType(),
            step.externalReferenceId(),
            step.startedAt(),
            step.completedAt(),
            step.createdAt(),
            now
        ));
    }

    @Override
    public void markStepCompensated(long stepId, String responsePayload, Instant now) {
        StepRecord step = findStepById(stepId).orElseThrow();
        replaceStep(step, new StepRecord(
            step.id(),
            step.checkoutSagaId(),
            step.stepName(),
            CheckoutStepStatus.COMPENSATED,
            step.stepCategory(),
            step.recoveryPolicy(),
            step.idempotencyKey(),
            step.requestPayload(),
            responsePayload,
            step.retryCount(),
            step.maxRetryCount(),
            step.nextRetryAt(),
            null,
            null,
            step.externalReferenceType(),
            step.externalReferenceId(),
            step.startedAt(),
            now,
            step.createdAt(),
            now
        ));
    }

    @Override
    public void markStepCompensationFailed(long stepId, String errorCode, String errorMessage, Instant now) {
        StepRecord step = findStepById(stepId).orElseThrow();
        replaceStep(step, new StepRecord(
            step.id(),
            step.checkoutSagaId(),
            step.stepName(),
            step.status(),
            step.stepCategory(),
            step.recoveryPolicy(),
            step.idempotencyKey(),
            step.requestPayload(),
            step.responsePayload(),
            step.retryCount(),
            step.maxRetryCount(),
            step.nextRetryAt(),
            errorCode,
            errorMessage,
            step.externalReferenceType(),
            step.externalReferenceId(),
            step.startedAt(),
            step.completedAt(),
            step.createdAt(),
            now
        ));
    }

    private void replaceStep(StepRecord oldStep, StepRecord newStep) {
        List<StepRecord> sagaSteps = steps.get(oldStep.checkoutSagaId());
        int index = sagaSteps.indexOf(oldStep);
        sagaSteps.set(index, newStep);
    }
}
