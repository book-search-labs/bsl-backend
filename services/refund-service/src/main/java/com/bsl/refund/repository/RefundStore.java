package com.bsl.refund.repository;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

public interface RefundStore {
    Optional<IdempotencyRecord> findIdempotency(String idempotencyKey);

    void insertIdempotency(String idempotencyKey, String operationType, String requestHash, String status);

    void markIdempotencyProcessing(String idempotencyKey);

    void updateIdempotencySucceeded(String idempotencyKey, String responsePayload);

    void updateIdempotencyFailed(String idempotencyKey, String errorMessage);

    void insertRefund(
        String refundId,
        String orderId,
        long checkoutId,
        String userId,
        String paymentId,
        String inventoryReservationId,
        String status,
        String reason,
        BigDecimal totalAmount,
        String currency,
        String requestPayload,
        String responsePayload
    );

    void insertRefundItem(String refundId, String bookId, int quantity, BigDecimal amount);

    Optional<RefundRecord> findRefund(String refundId);

    List<RefundRecord> findRefundsByOrderId(String orderId);

    List<RefundRecord> findAllRefunds();

    List<RefundItem> findRefundItems(String refundId);

    void updateRefundStatus(String refundId, String status, String responsePayload, String errorMessage);

    void insertRefundEvent(String refundId, String eventType, String payload);

    void insertOutboxEvent(String aggregateId, String eventType, String eventKey, String payload);
}
