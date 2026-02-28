package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.common.JsonUtils;
import com.bsl.commerce.config.CommerceProperties;
import com.bsl.commerce.repository.OrderRepository;
import com.bsl.commerce.repository.OpsTaskRepository;
import com.bsl.commerce.repository.PaymentRepository;
import com.bsl.commerce.repository.RefundRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RefundService {
    private static final Logger logger = LoggerFactory.getLogger(RefundService.class);
    private static final Set<String> SELLER_FAULT_REASON_CODES = Set.of(
        "DAMAGED",
        "DEFECTIVE",
        "WRONG_ITEM",
        "LATE_DELIVERY"
    );

    private final RefundRepository refundRepository;
    private final OrderRepository orderRepository;
    private final PaymentRepository paymentRepository;
    private final InventoryService inventoryService;
    private final OrderService orderService;
    private final OpsTaskRepository opsTaskRepository;
    private final CommerceProperties properties;
    private final ObjectMapper objectMapper;

    public RefundService(
        RefundRepository refundRepository,
        OrderRepository orderRepository,
        PaymentRepository paymentRepository,
        InventoryService inventoryService,
        OrderService orderService,
        OpsTaskRepository opsTaskRepository,
        CommerceProperties properties,
        ObjectMapper objectMapper
    ) {
        this.refundRepository = refundRepository;
        this.orderRepository = orderRepository;
        this.paymentRepository = paymentRepository;
        this.inventoryService = inventoryService;
        this.orderService = orderService;
        this.opsTaskRepository = opsTaskRepository;
        this.properties = properties;
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
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "주문 정보를 찾을 수 없습니다.");
        }
        String status = JdbcUtils.asString(order.get("status"));
        if ("REFUND_PENDING".equals(status)) {
            throw new ApiException(HttpStatus.CONFLICT, "refund_in_progress", "이미 환불 신청이 접수되어 처리 중입니다.");
        }
        if (!("PAID".equals(status)
            || "READY_TO_SHIP".equals(status)
            || "SHIPPED".equals(status)
            || "DELIVERED".equals(status)
            || "PARTIALLY_REFUNDED".equals(status))) {
            throw new ApiException(HttpStatus.CONFLICT, "invalid_state", "현재 주문 상태에서는 환불 신청이 불가능합니다.");
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
                    .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "not_found", "주문 도서 정보를 찾을 수 없습니다."));
                int qty = JdbcUtils.asInt(orderItem.get("qty"));
                int already = refundedQty.getOrDefault(item.orderItemId(), 0);
                int remaining = qty - already;
                if (item.qty() <= 0) {
                    throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "환불 수량은 1권 이상이어야 합니다.");
                }
                if (remaining <= 0) {
                    throw new ApiException(HttpStatus.CONFLICT, "refund_already_requested", "해당 도서는 이미 환불 신청이 접수되었습니다.");
                }
                if (item.qty() > remaining) {
                    throw new ApiException(HttpStatus.CONFLICT, "refund_exceeds", "환불 가능 수량을 초과했습니다. 주문 정보를 새로고침한 후 다시 시도해주세요.");
                }
                snapshots.add(snapshotFromOrderItem(orderItem, item.qty()));
            }
        }

        if (snapshots.isEmpty()) {
            throw new ApiException(HttpStatus.CONFLICT, "refund_already_requested", "환불 가능한 도서가 없습니다. 이미 환불 신청이 접수되었는지 확인해주세요.");
        }

        String normalizedReasonCode = normalizeReasonCode(reasonCode);
        RefundPricing pricing = calculateRefundPricing(order, orderItems, refundedQty, snapshots, normalizedReasonCode);
        long refundId = refundRepository.insertRefund(
            orderId,
            paymentId,
            "REQUESTED",
            normalizedReasonCode,
            reasonText,
            pricing.itemAmount(),
            pricing.shippingRefundAmount(),
            pricing.returnFeeAmount(),
            pricing.refundAmount(),
            pricing.policyCode(),
            idempotencyKey
        );

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
        refundRepository.insertRefundEvent(refundId, "REFUND_REQUESTED", JsonUtils.toJson(objectMapper, pricing.toPayload()));
        orderService.markRefundPending(orderId);
        return refundRepository.findRefund(refundId);
    }

    @Transactional
    public Map<String, Object> approveRefund(long refundId, long adminId) {
        Map<String, Object> refund = refundRepository.findRefund(refundId);
        if (refund == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "환불 정보를 찾을 수 없습니다.");
        }
        String status = JdbcUtils.asString(refund.get("status"));
        if (!"REQUESTED".equals(status)) {
            throw new ApiException(HttpStatus.CONFLICT, "invalid_state", "현재 상태에서는 환불 승인이 불가능합니다.");
        }
        refundRepository.updateRefundStatus(refundId, "APPROVED", adminId, null);
        refundRepository.insertRefundEvent(refundId, "REFUND_APPROVED", null);
        return refundRepository.findRefund(refundId);
    }

    @Transactional
    public Map<String, Object> processRefund(long refundId, String result) {
        Map<String, Object> refund = refundRepository.findRefund(refundId);
        if (refund == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "환불 정보를 찾을 수 없습니다.");
        }
        String status = JdbcUtils.asString(refund.get("status"));
        if (!"APPROVED".equals(status)) {
            throw new ApiException(HttpStatus.CONFLICT, "invalid_state", "현재 상태에서는 환불 처리를 진행할 수 없습니다.");
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
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "환불 정보를 찾을 수 없습니다.");
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

    private RefundPricing calculateRefundPricing(
        Map<String, Object> order,
        List<Map<String, Object>> orderItems,
        Map<Long, Integer> refundedQty,
        List<RefundItemSnapshot> requestedSnapshots,
        String reasonCode
    ) {
        int itemAmount = requestedSnapshots.stream().mapToInt(RefundItemSnapshot::amount).sum();
        boolean fullRefundAfterThisRequest = isFullRefundAfterThisRequest(orderItems, refundedQty, requestedSnapshots);
        String orderStatus = JdbcUtils.asString(order.get("status"));
        int orderShippingFee = Math.max(0, JdbcUtils.asInt(order.get("shipping_fee")) == null ? 0 : JdbcUtils.asInt(order.get("shipping_fee")));

        Map<String, Object> refundedAmounts = refundRepository.sumRefundAmountsByOrder(JdbcUtils.asLong(order.get("order_id")));
        int alreadyShippingRefunded = Math.max(
            0,
            JdbcUtils.asInt(refundedAmounts.get("shipping_refund_amount")) == null
                ? 0
                : JdbcUtils.asInt(refundedAmounts.get("shipping_refund_amount"))
        );
        int remainingShippingRefundable = Math.max(0, orderShippingFee - alreadyShippingRefunded);

        int shippingRefundAmount = 0;
        int returnFeeAmount = 0;
        String policyCode;

        if ("PAID".equals(orderStatus) || "READY_TO_SHIP".equals(orderStatus)) {
            policyCode = fullRefundAfterThisRequest ? "PRE_SHIPMENT_FULL_REFUND" : "PRE_SHIPMENT_PARTIAL_REFUND";
            if (fullRefundAfterThisRequest) {
                shippingRefundAmount = remainingShippingRefundable;
            }
        } else if ("SHIPPED".equals(orderStatus) || "DELIVERED".equals(orderStatus) || "PARTIALLY_REFUNDED".equals(orderStatus)) {
            if (isSellerFaultReason(reasonCode)) {
                policyCode = fullRefundAfterThisRequest ? "SELLER_FAULT_FULL_RETURN" : "SELLER_FAULT_PARTIAL_RETURN";
                if (fullRefundAfterThisRequest) {
                    shippingRefundAmount = remainingShippingRefundable;
                }
            } else {
                policyCode = "CUSTOMER_REMORSE_RETURN";
                returnFeeAmount = resolveReturnFee(order);
            }
        } else {
            policyCode = "STANDARD_REFUND";
        }

        int grossRefund = itemAmount + shippingRefundAmount;
        int appliedReturnFee = Math.min(returnFeeAmount, grossRefund);
        int netRefundAmount = Math.max(0, grossRefund - appliedReturnFee);

        return new RefundPricing(itemAmount, shippingRefundAmount, appliedReturnFee, netRefundAmount, policyCode);
    }

    private boolean isFullRefundAfterThisRequest(
        List<Map<String, Object>> orderItems,
        Map<Long, Integer> refundedQty,
        List<RefundItemSnapshot> requestedSnapshots
    ) {
        Map<Long, Integer> requestedQtyByOrderItem = new HashMap<>();
        for (RefundItemSnapshot snapshot : requestedSnapshots) {
            requestedQtyByOrderItem.merge(snapshot.orderItemId(), snapshot.qty(), Integer::sum);
        }

        for (Map<String, Object> orderItem : orderItems) {
            long orderItemId = JdbcUtils.asLong(orderItem.get("order_item_id"));
            int totalQty = JdbcUtils.asInt(orderItem.get("qty"));
            int alreadyRefundedQty = refundedQty.getOrDefault(orderItemId, 0);
            int requestedQty = requestedQtyByOrderItem.getOrDefault(orderItemId, 0);
            if (alreadyRefundedQty + requestedQty < totalQty) {
                return false;
            }
        }
        return true;
    }

    private String normalizeReasonCode(String reasonCode) {
        if (reasonCode == null || reasonCode.isBlank()) {
            return "OTHER";
        }
        return reasonCode.trim().toUpperCase();
    }

    private boolean isSellerFaultReason(String reasonCode) {
        return SELLER_FAULT_REASON_CODES.contains(normalizeReasonCode(reasonCode));
    }

    private int resolveReturnFee(Map<String, Object> order) {
        String shippingMode = JdbcUtils.asString(order.get("shipping_mode"));
        if ("FAST".equalsIgnoreCase(shippingMode)) {
            return properties.getCart().getFastShippingFee();
        }
        Integer orderShippingFee = JdbcUtils.asInt(order.get("shipping_fee"));
        if (orderShippingFee != null && orderShippingFee > 0) {
            return orderShippingFee;
        }
        return properties.getCart().getBaseShippingFee();
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

    private record RefundPricing(
        int itemAmount,
        int shippingRefundAmount,
        int returnFeeAmount,
        int refundAmount,
        String policyCode
    ) {
        private Map<String, Object> toPayload() {
            Map<String, Object> payload = new HashMap<>();
            payload.put("item_amount", itemAmount);
            payload.put("shipping_refund_amount", shippingRefundAmount);
            payload.put("return_fee_amount", returnFeeAmount);
            payload.put("refund_amount", refundAmount);
            payload.put("policy_code", policyCode);
            return payload;
        }
    }
}
