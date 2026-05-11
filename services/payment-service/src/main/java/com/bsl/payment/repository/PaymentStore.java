package com.bsl.payment.repository;

import java.math.BigDecimal;
import java.util.Optional;

public interface PaymentStore {
    Optional<IdempotencyRecord> findIdempotency(String idempotencyKey);

    void insertIdempotency(String idempotencyKey, String operationType, String requestHash, String status);

    void updateIdempotencySucceeded(String idempotencyKey, String responsePayload);

    void insertAuthorization(
        String paymentId,
        long checkoutId,
        String orderId,
        BigDecimal amount,
        String currency,
        String status,
        String idempotencyKey,
        String pgTransactionId,
        String responsePayload
    );

    void insertCancellation(
        String cancellationId,
        String paymentId,
        long checkoutId,
        String status,
        String idempotencyKey,
        String responsePayload
    );
}

