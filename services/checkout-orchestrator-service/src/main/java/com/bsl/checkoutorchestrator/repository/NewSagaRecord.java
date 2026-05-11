package com.bsl.checkoutorchestrator.repository;

import com.bsl.checkoutorchestrator.domain.CheckoutSagaStatus;
import java.time.Instant;

public record NewSagaRecord(
    String checkoutKey,
    String userId,
    CheckoutSagaStatus status,
    String currentStep,
    String requestPayload,
    String contextPayload,
    String errorCode,
    String errorMessage,
    long version,
    Instant createdAt,
    Instant updatedAt
) {
}

