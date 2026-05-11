package com.bsl.payment.repository;

public record IdempotencyRecord(
    String idempotencyKey,
    String operationType,
    String requestHash,
    String status,
    String responsePayload,
    String errorMessage
) {
}

