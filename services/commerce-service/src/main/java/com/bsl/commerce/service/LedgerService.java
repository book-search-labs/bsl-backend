package com.bsl.commerce.service;

import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.config.PaymentProperties;
import com.bsl.commerce.repository.LedgerRepository;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LedgerService {
    private final LedgerRepository ledgerRepository;
    private final PaymentProperties paymentProperties;

    public LedgerService(LedgerRepository ledgerRepository, PaymentProperties paymentProperties) {
        this.ledgerRepository = ledgerRepository;
        this.paymentProperties = paymentProperties;
    }

    @Transactional
    public void recordPaymentCaptured(long paymentId, long orderId, List<Map<String, Object>> orderItems, String currency) {
        if (orderItems == null || orderItems.isEmpty()) {
            return;
        }
        String resolvedCurrency = currency == null ? "KRW" : currency;
        Instant occurredAt = Instant.now();
        for (Map<String, Object> item : orderItems) {
            long sellerId = JdbcUtils.asLong(item.get("seller_id"));
            long orderItemId = JdbcUtils.asLong(item.get("order_item_id"));
            int itemAmount = JdbcUtils.asInt(item.get("item_amount")) == null
                ? JdbcUtils.asInt(item.get("qty")) * JdbcUtils.asInt(item.get("unit_price"))
                : JdbcUtils.asInt(item.get("item_amount"));
            int pgFee = -Math.round(itemAmount * (float) paymentProperties.getPgFeeRatePercent() / 100.0f);
            int platformFee = -Math.round(itemAmount * (float) paymentProperties.getPlatformFeeRatePercent() / 100.0f);

            ledgerRepository.insertEntry(
                sellerId,
                orderId,
                paymentId,
                "SALE",
                itemAmount,
                resolvedCurrency,
                occurredAt,
                "payment:" + paymentId + ":item:" + orderItemId + ":sale"
            );
            ledgerRepository.insertEntry(
                sellerId,
                orderId,
                paymentId,
                "PG_FEE",
                pgFee,
                resolvedCurrency,
                occurredAt,
                "payment:" + paymentId + ":item:" + orderItemId + ":pg_fee"
            );
            ledgerRepository.insertEntry(
                sellerId,
                orderId,
                paymentId,
                "PLATFORM_FEE",
                platformFee,
                resolvedCurrency,
                occurredAt,
                "payment:" + paymentId + ":item:" + orderItemId + ":platform_fee"
            );
        }
    }

    @Transactional
    public void recordRefund(
        long refundId,
        long orderId,
        Long paymentId,
        String currency,
        List<Map<String, Object>> refundItems,
        Map<Long, Long> sellerByOrderItem
    ) {
        if (refundItems == null || refundItems.isEmpty()) {
            return;
        }
        String resolvedCurrency = currency == null ? "KRW" : currency;
        Instant occurredAt = Instant.now();
        for (Map<String, Object> item : refundItems) {
            long orderItemId = JdbcUtils.asLong(item.get("order_item_id"));
            long sellerId = sellerByOrderItem.getOrDefault(orderItemId, 1L);
            int amount = JdbcUtils.asInt(item.get("amount")) == null ? 0 : JdbcUtils.asInt(item.get("amount"));
            ledgerRepository.insertEntry(
                sellerId,
                orderId,
                paymentId,
                "REFUND",
                -Math.abs(amount),
                resolvedCurrency,
                occurredAt,
                "refund:" + refundId + ":item:" + orderItemId + ":refund"
            );
        }
    }
}
