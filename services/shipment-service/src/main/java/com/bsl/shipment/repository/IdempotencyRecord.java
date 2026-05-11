package com.bsl.shipment.repository;

public record IdempotencyRecord(
    String idempotencyKey,
    String operationType,
    String requestHash,
    String status,
    String responsePayload,
    String errorMessage
) {
}

