package com.bsl.checkoutorchestrator.client;

import com.bsl.checkoutorchestrator.domain.CheckoutStepName;
import java.util.Map;
import java.util.Optional;

public interface CheckoutDownstreamClient {
    Map<String, Object> execute(
        CheckoutStepName stepName,
        Map<String, Object> request,
        String idempotencyKey,
        String traceId,
        String requestId
    );

    Optional<Map<String, Object>> reconcile(
        CheckoutStepName stepName,
        String idempotencyKey,
        String traceId,
        String requestId
    );

    Map<String, Object> compensate(
        CheckoutStepName stepName,
        Map<String, Object> request,
        String idempotencyKey,
        String traceId,
        String requestId
    );
}
