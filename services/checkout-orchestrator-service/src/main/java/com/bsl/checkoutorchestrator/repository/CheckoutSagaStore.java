package com.bsl.checkoutorchestrator.repository;

import com.bsl.checkoutorchestrator.domain.CheckoutSagaStatus;
import com.bsl.checkoutorchestrator.domain.CheckoutStepName;
import com.bsl.checkoutorchestrator.domain.CheckoutStepStatus;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

public interface CheckoutSagaStore {
    Optional<SagaRecord> findSagaByCheckoutKey(String checkoutKey);

    Optional<SagaRecord> findSagaById(long checkoutId);

    List<SagaRecord> findSagas(CheckoutSagaStatus status, int limit);

    List<StepRecord> findStepsBySagaId(long checkoutSagaId);

    List<OutboxEventRecord> findOutboxEventsByAggregate(String aggregateType, long aggregateId);

    List<StepRecord> findDueSteps(Instant now, int limit);

    Optional<StepRecord> findStepById(long stepId);

    Optional<StepRecord> findStepBySagaIdAndName(long checkoutSagaId, CheckoutStepName stepName);

    long insertSaga(NewSagaRecord saga);

    void insertStep(NewStepRecord step);

    void insertOutboxEvent(NewOutboxEventRecord event);

    boolean outboxEventExists(String eventKey);

    int claimStepForProcessing(long stepId, CheckoutStepStatus expectedStatus, Instant now);

    void updateSagaStatus(long sagaId, CheckoutSagaStatus status, CheckoutStepName currentStep, String errorCode, String errorMessage, Instant now);

    void updateSagaContext(long sagaId, String contextPayload, Instant now);

    void markStepSucceeded(long stepId, String responsePayload, Instant now);

    void markStepFailedRetrying(long stepId, int retryCount, Instant nextRetryAt, String errorCode, String errorMessage, Instant now);

    void markStepUnknown(long stepId, int retryCount, Instant nextRetryAt, String errorCode, String errorMessage, Instant now);

    void markStepManualReview(long stepId, String errorCode, String errorMessage, Instant now);

    void resetStepForManualRetry(long stepId, Instant now);

    void scheduleUnknownReconciliation(long stepId, Instant now);

    void markStepCompensating(long stepId, Instant now);

    void markStepCompensated(long stepId, String responsePayload, Instant now);

    void markStepCompensationFailed(long stepId, String errorCode, String errorMessage, Instant now);
}
