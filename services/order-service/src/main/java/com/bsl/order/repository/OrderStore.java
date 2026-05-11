package com.bsl.order.repository;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public interface OrderStore {
    Optional<IdempotencyRecord> findIdempotency(String idempotencyKey);

    void insertIdempotency(String idempotencyKey, String operationType, String requestHash, String status);

    void updateIdempotencySucceeded(String idempotencyKey, String responsePayload);

    void insertOrder(String orderId, String userId, long checkoutId, String status, BigDecimal totalAmount, String currency);

    void insertOrderLine(String orderId, String bookId, String title, int quantity, BigDecimal unitPrice);

    Optional<Map<String, Object>> findOrder(String orderId);

    List<Map<String, Object>> findOrderLines(String orderId);
}

