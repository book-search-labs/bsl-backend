package com.bsl.refund.repository;

import java.math.BigDecimal;

public record RefundItem(
    String refundId,
    String bookId,
    int quantity,
    BigDecimal amount
) {
}
