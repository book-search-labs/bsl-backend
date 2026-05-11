package com.bsl.refund.repository;

import java.math.BigDecimal;

public record RefundRecord(
    long id,
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
    String responsePayload,
    String errorMessage
) {
}
