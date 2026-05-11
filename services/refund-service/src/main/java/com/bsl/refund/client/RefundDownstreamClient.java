package com.bsl.refund.client;

import java.util.Map;
import java.util.Optional;

public interface RefundDownstreamClient {
    Map<String, Object> cancelPayment(Map<String, Object> request, String idempotencyKey, String traceId, String requestId);

    Optional<Map<String, Object>> findPaymentByIdempotencyKey(String idempotencyKey, String traceId, String requestId);

    Map<String, Object> releaseInventory(Map<String, Object> request, String idempotencyKey, String traceId, String requestId);

    Optional<Map<String, Object>> findInventoryByIdempotencyKey(String idempotencyKey, String traceId, String requestId);
}
