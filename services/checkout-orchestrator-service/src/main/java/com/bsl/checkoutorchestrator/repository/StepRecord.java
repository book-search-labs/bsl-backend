package com.bsl.checkoutorchestrator.repository;

import com.bsl.checkoutorchestrator.domain.CheckoutStepCategory;
import com.bsl.checkoutorchestrator.domain.CheckoutStepName;
import com.bsl.checkoutorchestrator.domain.CheckoutStepStatus;
import com.bsl.checkoutorchestrator.domain.RecoveryPolicy;
import java.time.Instant;

public record StepRecord(
    long id,
    long checkoutSagaId,
    CheckoutStepName stepName,
    CheckoutStepStatus status,
    CheckoutStepCategory stepCategory,
    RecoveryPolicy recoveryPolicy,
    String idempotencyKey,
    String requestPayload,
    String responsePayload,
    int retryCount,
    int maxRetryCount,
    Instant nextRetryAt,
    String errorCode,
    String errorMessage,
    String externalReferenceType,
    String externalReferenceId,
    Instant startedAt,
    Instant completedAt,
    Instant createdAt,
    Instant updatedAt
) {
}

