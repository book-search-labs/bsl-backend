package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.common.JsonUtils;
import com.bsl.commerce.repository.OrderRepository;
import com.bsl.commerce.repository.PaymentRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentService {
    private final PaymentRepository paymentRepository;
    private final OrderRepository orderRepository;
    private final OrderService orderService;
    private final InventoryService inventoryService;
    private final ObjectMapper objectMapper;

    public PaymentService(
        PaymentRepository paymentRepository,
        OrderRepository orderRepository,
        OrderService orderService,
        InventoryService inventoryService,
        ObjectMapper objectMapper
    ) {
        this.paymentRepository = paymentRepository;
        this.orderRepository = orderRepository;
        this.orderService = orderService;
        this.inventoryService = inventoryService;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Map<String, Object> createPayment(long orderId, int amount, String method, String idempotencyKey) {
        if (idempotencyKey != null) {
            Map<String, Object> existing = paymentRepository.findPaymentByIdempotencyKey(idempotencyKey);
            if (existing != null) {
                return existing;
            }
        }

        Map<String, Object> order = orderRepository.findOrderById(orderId);
        if (order == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "order not found");
        }
        String status = JdbcUtils.asString(order.get("status"));
        if (!"PAYMENT_PENDING".equals(status) && !"CREATED".equals(status)) {
            throw new ApiException(HttpStatus.CONFLICT, "invalid_state", "order not ready for payment");
        }
        int totalAmount = JdbcUtils.asInt(order.get("total_amount")) == null ? 0 : JdbcUtils.asInt(order.get("total_amount"));
        if (amount != totalAmount) {
            throw new ApiException(HttpStatus.CONFLICT, "amount_mismatch", "amount does not match order total");
        }

        String currency = JdbcUtils.asString(order.get("currency"));
        if (currency == null) {
            currency = "KRW";
        }
        long paymentId = paymentRepository.insertPayment(
            orderId,
            method == null ? "CARD" : method,
            "INITIATED",
            amount,
            currency,
            "MOCK",
            null,
            idempotencyKey
        );

        paymentRepository.insertPaymentEvent(paymentId, "PAYMENT_INITIATED", null, null);
        return paymentRepository.findPayment(paymentId);
    }

    @Transactional
    public Map<String, Object> mockComplete(long paymentId, String result) {
        Map<String, Object> payment = paymentRepository.findPayment(paymentId);
        if (payment == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "payment not found");
        }
        String status = JdbcUtils.asString(payment.get("status"));
        if ("CAPTURED".equals(status) || "FAILED".equals(status) || "CANCELED".equals(status)) {
            return payment;
        }

        boolean success = "SUCCESS".equalsIgnoreCase(result);
        long orderId = JdbcUtils.asLong(payment.get("order_id"));

        if (success) {
            paymentRepository.updatePaymentStatus(paymentId, "CAPTURED", "mock-" + paymentId, null);
            paymentRepository.insertPaymentEvent(paymentId, "CAPTURE_SUCCEEDED", null, null);
            orderService.markPaid(orderId, String.valueOf(paymentId));

            List<Map<String, Object>> items = orderRepository.findOrderItems(orderId);
            for (Map<String, Object> item : items) {
                long skuId = JdbcUtils.asLong(item.get("sku_id"));
                long sellerId = JdbcUtils.asLong(item.get("seller_id"));
                int qty = JdbcUtils.asInt(item.get("qty"));
                long orderItemId = JdbcUtils.asLong(item.get("order_item_id"));
                String deductKey = "payment_" + paymentId + "_deduct_" + orderItemId;
                inventoryService.deduct(skuId, sellerId, qty, deductKey, "ORDER", String.valueOf(orderId));
            }
        } else {
            paymentRepository.updatePaymentStatus(paymentId, "FAILED", null, "mock_failed");
            paymentRepository.insertPaymentEvent(paymentId, "CAPTURE_FAILED", null, null);
        }

        return paymentRepository.findPayment(paymentId);
    }

    @Transactional
    public void handleWebhook(String provider, Map<String, Object> payload, String providerEventId) {
        String payloadJson = JsonUtils.toJson(objectMapper, payload);
        Long paymentId = null;
        if (payload != null) {
            Object value = payload.getOrDefault("payment_id", payload.get("paymentId"));
            paymentId = JdbcUtils.asLong(value);
        }
        if (paymentId == null) {
            return;
        }
        try {
            paymentRepository.insertPaymentEvent(paymentId, "WEBHOOK_RECEIVED", providerEventId, payloadJson);
        } catch (org.springframework.dao.DuplicateKeyException ignored) {
            // idempotent webhook
        }
    }

    public Map<String, Object> getPayment(long paymentId) {
        Map<String, Object> payment = paymentRepository.findPayment(paymentId);
        if (payment == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "payment not found");
        }
        return payment;
    }

    @Transactional
    public Map<String, Object> cancelPayment(long paymentId, String reason) {
        Map<String, Object> payment = paymentRepository.findPayment(paymentId);
        if (payment == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "payment not found");
        }
        String status = JdbcUtils.asString(payment.get("status"));
        if ("CANCELED".equals(status)) {
            return payment;
        }
        paymentRepository.updatePaymentStatus(paymentId, "CANCELED", JdbcUtils.asString(payment.get("provider_payment_id")),
            reason);
        paymentRepository.insertPaymentEvent(paymentId, "PAYMENT_CANCELED", null, null);
        return paymentRepository.findPayment(paymentId);
    }

    public List<Map<String, Object>> listPayments(int limit) {
        int resolved = Math.min(Math.max(limit, 1), 200);
        return paymentRepository.listPayments(resolved);
    }
}
