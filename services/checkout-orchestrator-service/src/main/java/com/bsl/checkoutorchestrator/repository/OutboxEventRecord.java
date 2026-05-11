package com.bsl.checkoutorchestrator.repository;

import com.bsl.checkoutorchestrator.domain.OutboxStatus;
import java.time.Instant;

public record OutboxEventRecord(
    long id,
    String aggregateType,
    long aggregateId,
    String eventType,
    String eventKey,
    String payload,
    OutboxStatus status,
    int retryCount,
    Instant nextRetryAt,
    String lockedBy,
    Instant lockedUntil,
    String errorMessage,
    Instant createdAt,
    Instant updatedAt,
    Instant publishedAt
) {
}

