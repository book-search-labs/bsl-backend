package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.common.JsonUtils;
import com.bsl.commerce.repository.OrderRepository;
import com.bsl.commerce.repository.OpsTaskRepository;
import com.bsl.commerce.repository.PaymentRepository;
import com.bsl.commerce.repository.RefundRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RefundService {
    private static final Logger logger = LoggerFactory.getLogger(RefundService.class);

    private final RefundRepository refundRepository;
    private final OrderRepository orderRepository;
    private final PaymentRepository paymentRepository;
    private final InventoryService inventoryService;
    private final OrderService orderService;
    private final OpsTaskRepository opsTaskRepository;
    private final ObjectMapper objectMapper;

    public RefundService(
        RefundRepository refundRepository,
        OrderRepository orderRepository,
        PaymentRepository paymentRepository,
        InventoryService inventoryService,
        OrderService orderService,
        OpsTaskRepository opsTaskRepository,
        ObjectMapper objectMapper
    ) {
        this.refundRepository = refundRepository;
        this.orderRepository = orderRepository;
        this.paymentRepository = paymentRepository;
        this.inventoryService = inventoryService;
        this.orderService = orderService;
        this.opsTaskRepository = opsTaskRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Map<String, Object> createRefund(
        long orderId,
        List<RefundItemRequest> items,
        String reasonCode,
        String reasonText,
        String idempotencyKey
    ) {
        if (idempotencyKey != null) {
            Map<String, Object> existing = refundRepository.findRefundByIdempotencyKey(idempotencyKey);
            if (existing != null) {
                return existing;
            }
        }

        Map<String, Object> order = orderRepository.findOrderById(orderId);
        if (order == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "order not found");
        }
        String status = JdbcUtils.asString(order.get("status"));
        if (!("PAID".equals(status)
            || "SHIPPED".equals(status)
            || "DELIVERED".equals(status)
            || "PARTIALLY_REFUNDED".equals(status))) {
            throw new ApiException(HttpStatus.CONFLICT, "invalid_state", "order not refundable");
        }

        Map<String, Object> payment = paymentRepository.findLatestPaymentByOrder(orderId);
        Long paymentId = payment == null ? null : JdbcUtils.asLong(payment.get("payment_id"));

        List<Map<String, Object>> orderItems = orderRepository.findOrderItems(orderId);
        Map<Long, Integer> refundedQty = new HashMap<>();
        for (Map<String, Object> row : refundRepository.sumRefundedQtyByOrder(orderId)) {
            refundedQty.put(JdbcUtils.asLong(row.get("order_item_id")), JdbcUtils.asInt(row.get("refunded_qty")));
        }

        List<RefundItemSnapshot> snapshots = new ArrayList<>();
        if (items == null || items.isEmpty()) {
            for (Map<String, Object> orderItem : orderItems) {
                long orderItemId = JdbcUtils.asLong(orderItem.get("order_item_id"));
                int qty = JdbcUtils.asInt(orderItem.get("qty"));
                int already = refundedQty.getOrDefault(orderItemId, 0);
                int remaining = qty - already;
                if (remaining <= 0) {
                    continue;
                }
                snapshots.add(snapshotFromOrderItem(orderItem, remaining));
            }
        } else {
            for (RefundItemRequest item : items) {
                Map<String, Object> orderItem = orderItems.stream()
                    .filter(row -> JdbcUtils.asLong(row.get("order_item_id")) == item.orderItemId())
                    .findFirst()
                    .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "not_found", "order item not found"));
                int qty = JdbcUtils.asInt(orderItem.get("qty"));
                int already = refundedQty.getOrDefault(item.orderItemId(), 0);
                int remaining = qty - already;
                if (item.qty() <= 0 || item.qty() > remaining) {
                    throw new ApiException(HttpStatus.CONFLICT, "refund_exceeds", "refund qty exceeds remaining");
                }
                snapshots.add(snapshotFromOrderItem(orderItem, item.qty()));
            }
        }

        if (snapshots.isEmpty()) {
            throw new ApiException(HttpStatus.CONFLICT, "refund_exceeds", "no refundable items");
        }

        int totalAmount = snapshots.stream().mapToInt(RefundItemSnapshot::amount).sum();
        long refundId = refundRepository.insertRefund(orderId, paymentId, "REQUESTED", reasonCode, reasonText, totalAmount,
            idempotencyKey);

        List<RefundRepository.RefundItemInsert> inserts = new ArrayList<>();
        for (RefundItemSnapshot snapshot : snapshots) {
            inserts.add(new RefundRepository.RefundItemInsert(
                refundId,
                snapshot.orderItemId(),
                snapshot.skuId(),
                snapshot.qty(),
                snapshot.amount()
            ));
        }
        refundRepository.insertRefundItems(inserts);
        refundRepository.insertRefundEvent(refundId, "REFUND_REQUESTED", null);
        return refundRepository.findRefund(refundId);
    }

    @Transactional
    public Map<String, Object> approveRefund(long refundId, long adminId) {
        Map<String, Object> refund = refundRepository.findRefund(refundId);
        if (refund == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "refund not found");
        }
        String status = JdbcUtils.asString(refund.get("status"));
        if (!"REQUESTED".equals(status)) {
            throw new ApiException(HttpStatus.CONFLICT, "invalid_state", "refund cannot be approved");
        }
        refundRepository.updateRefundStatus(refundId, "APPROVED", adminId, null);
        refundRepository.insertRefundEvent(refundId, "REFUND_APPROVED", null);
        return refundRepository.findRefund(refundId);
    }

    @Transactional
    public Map<String, Object> processRefund(long refundId, String result) {
        Map<String, Object> refund = refundRepository.findRefund(refundId);
        if (refund == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "refund not found");
        }
        String status = JdbcUtils.asString(refund.get("status"));
        if (!"APPROVED".equals(status)) {
            throw new ApiException(HttpStatus.CONFLICT, "invalid_state", "refund not ready to process");
        }

        refundRepository.updateRefundStatus(refundId, "PROCESSING", JdbcUtils.asLong(refund.get("approved_by_admin_id")),
            null);
        refundRepository.insertRefundEvent(refundId, "PROVIDER_REFUND_REQUESTED", null);

        boolean success = "FAIL".equalsIgnoreCase(result) ? false : true;
        if (!success) {
            refundRepository.updateRefundStatus(refundId, "FAILED", JdbcUtils.asLong(refund.get("approved_by_admin_id")),
                null);
            refundRepository.insertRefundEvent(refundId, "PROVIDER_REFUND_FAILED", null);
            return refundRepository.findRefund(refundId);
        }

        refundRepository.updateRefundStatus(refundId, "REFUNDED", JdbcUtils.asLong(refund.get("approved_by_admin_id")),
            "mock-refund-" + refundId);
        refundRepository.insertRefundEvent(refundId, "PROVIDER_REFUND_SUCCEEDED", null);

        List<Map<String, Object>> items = refundRepository.listRefundItems(refundId);
        Map<Long, Long> sellerByOrderItem = new HashMap<>();
        for (Map<String, Object> orderItem : orderRepository.findOrderItems(JdbcUtils.asLong(refund.get("order_id")))) {
            sellerByOrderItem.put(JdbcUtils.asLong(orderItem.get("order_item_id")), JdbcUtils.asLong(orderItem.get("seller_id")));
        }
        boolean restockFailed = false;
        for (Map<String, Object> item : items) {
            long skuId = JdbcUtils.asLong(item.get("sku_id"));
            int qty = JdbcUtils.asInt(item.get("qty"));
            long orderItemId = JdbcUtils.asLong(item.get("order_item_id"));
            try {
                String restockKey = "refund_" + refundId + "_restock_" + orderItemId;
                long sellerId = sellerByOrderItem.getOrDefault(orderItemId, 1L);
                inventoryService.restock(skuId, sellerId, qty, restockKey, "REFUND", String.valueOf(refundId));
            } catch (Exception ex) {
                restockFailed = true;
                logger.error("restock_failed refund_id={} order_item_id={} error={}", refundId, orderItemId,
                    ex.getMessage());
            }
        }

        if (restockFailed) {
            Map<String, Object> payload = Map.of(
                "refund_id", refundId,
                "order_id", JdbcUtils.asLong(refund.get("order_id")),
                "message", "inventory restock failed"
            );
            opsTaskRepository.insertTask("INVENTORY_RESTOCK", "OPEN", JsonUtils.toJson(objectMapper, payload));
        }

        boolean partial = isPartialRefund(JdbcUtils.asLong(refund.get("order_id")));
        orderService.markRefunded(JdbcUtils.asLong(refund.get("order_id")), partial);

        return refundRepository.findRefund(refundId);
    }

    public Map<String, Object> getRefund(long refundId) {
        Map<String, Object> refund = refundRepository.findRefund(refundId);
        if (refund == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "refund not found");
        }
        return refund;
    }

    public List<Map<String, Object>> listRefundsByOrder(long orderId) {
        return refundRepository.listRefundsByOrder(orderId);
    }

    public List<Map<String, Object>> listRefunds(int limit) {
        int resolved = Math.min(Math.max(limit, 1), 200);
        return refundRepository.listRefunds(resolved);
    }

    public List<Map<String, Object>> listRefundItems(long refundId) {
        return refundRepository.listRefundItems(refundId);
    }

    private RefundItemSnapshot snapshotFromOrderItem(Map<String, Object> orderItem, int qty) {
        long orderItemId = JdbcUtils.asLong(orderItem.get("order_item_id"));
        Long skuId = JdbcUtils.asLong(orderItem.get("sku_id"));
        int unitPrice = JdbcUtils.asInt(orderItem.get("unit_price"));
        int amount = unitPrice * qty;
        return new RefundItemSnapshot(orderItemId, skuId, qty, amount);
    }

    private boolean isPartialRefund(long orderId) {
        List<Map<String, Object>> orderItems = orderRepository.findOrderItems(orderId);
        Map<Long, Integer> refunded = new HashMap<>();
        for (Map<String, Object> row : refundRepository.sumRefundedQtyByOrder(orderId)) {
            refunded.put(JdbcUtils.asLong(row.get("order_item_id")), JdbcUtils.asInt(row.get("refunded_qty")));
        }
        for (Map<String, Object> item : orderItems) {
            long orderItemId = JdbcUtils.asLong(item.get("order_item_id"));
            int qty = JdbcUtils.asInt(item.get("qty"));
            int refundedQty = refunded.getOrDefault(orderItemId, 0);
            if (refundedQty < qty) {
                return true;
            }
        }
        return false;
    }

    public record RefundItemRequest(long orderItemId, int qty) {
    }

    private record RefundItemSnapshot(long orderItemId, Long skuId, int qty, int amount) {
    }
}
