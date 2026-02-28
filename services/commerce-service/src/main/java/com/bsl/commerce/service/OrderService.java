package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.common.JsonUtils;
import com.bsl.commerce.common.PriceUtils;
import com.bsl.commerce.config.CommerceProperties;
import com.bsl.commerce.repository.AddressRepository;
import com.bsl.commerce.repository.CartRepository;
import com.bsl.commerce.repository.OrderRepository;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private static final int DEFAULT_LIST_LIMIT = 20;

    private final OrderRepository orderRepository;
    private final CartRepository cartRepository;
    private final CatalogService catalogService;
    private final InventoryService inventoryService;
    private final AddressRepository addressRepository;
    private final CommerceProperties properties;
    private final ObjectMapper objectMapper;

    public OrderService(
        OrderRepository orderRepository,
        CartRepository cartRepository,
        CatalogService catalogService,
        InventoryService inventoryService,
        AddressRepository addressRepository,
        CommerceProperties properties,
        ObjectMapper objectMapper
    ) {
        this.orderRepository = orderRepository;
        this.cartRepository = cartRepository;
        this.catalogService = catalogService;
        this.inventoryService = inventoryService;
        this.addressRepository = addressRepository;
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Map<String, Object> createOrder(
        long userId,
        Long cartId,
        List<OrderItemRequest> items,
        Long shippingAddressId,
        Map<String, Object> shippingSnapshot,
        String shippingMode,
        String paymentMethod,
        String idempotencyKey
    ) {
        if (idempotencyKey != null) {
            Map<String, Object> existing = orderRepository.findOrderByIdempotencyKey(idempotencyKey);
            if (existing != null) {
                return existing;
            }
        }

        List<OrderItemRequest> resolvedItems = new ArrayList<>();
        Long resolvedCartId = cartId;
        if (resolvedCartId != null) {
            Map<String, Object> cart = cartRepository.findCartById(resolvedCartId);
            if (cart == null || JdbcUtils.asLong(cart.get("user_id")) != userId) {
                throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "장바구니를 찾을 수 없습니다.");
            }
            List<Map<String, Object>> cartItems = cartRepository.listCartItems(resolvedCartId);
            if (cartItems.isEmpty()) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "장바구니가 비어 있습니다.");
            }
            for (Map<String, Object> cartItem : cartItems) {
                resolvedItems.add(new OrderItemRequest(
                    JdbcUtils.asLong(cartItem.get("sku_id")),
                    JdbcUtils.asLong(cartItem.get("seller_id")),
                    JdbcUtils.asInt(cartItem.get("qty")),
                    JdbcUtils.asLong(cartItem.get("offer_id")),
                    PriceUtils.normalizeBookPrice(JdbcUtils.asInt(cartItem.get("unit_price")))
                ));
            }
        } else if (items != null && !items.isEmpty()) {
            resolvedItems.addAll(items);
        } else {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "cart_id 또는 items가 필요합니다.");
        }

        List<OrderItemSnapshot> snapshots = new ArrayList<>();
        int totalAmount = 0;

        for (OrderItemRequest item : resolvedItems) {
            if (item.skuId() == null || item.sellerId() == null || item.qty() == null) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "주문 항목 필수값이 누락되었습니다.");
            }
            if (item.qty() <= 0) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "수량은 1개 이상이어야 합니다.");
            }
            Map<String, Object> currentOffer = catalogService.requireCurrentOfferBySkuId(item.skuId());
            Long offerId = JdbcUtils.asLong(currentOffer.get("offer_id"));
            Integer unitPrice = PriceUtils.normalizeBookPrice(JdbcUtils.asInt(currentOffer.get("effective_price")));
            Integer requestUnitPrice = PriceUtils.normalizeBookPrice(item.unitPrice());
            String currency = JdbcUtils.asString(currentOffer.get("currency"));
            Long currentSellerId = JdbcUtils.asLong(currentOffer.get("seller_id"));
            if (currentSellerId != null && currentSellerId != item.sellerId()) {
                throw new ApiException(HttpStatus.CONFLICT, "seller_mismatch", "판매자 정보가 일치하지 않습니다.");
            }

            if (item.offerId() != null && offerId != null && !offerId.equals(item.offerId())) {
                throw new ApiException(HttpStatus.CONFLICT, "price_changed", "판매 정보가 변경되었습니다. 장바구니를 새로고침해주세요.");
            }
            if (requestUnitPrice != null && unitPrice != null && !unitPrice.equals(requestUnitPrice)) {
                throw new ApiException(HttpStatus.CONFLICT, "price_changed", "도서 금액이 변경되었습니다. 장바구니를 새로고침해주세요.");
            }

            int itemAmount = (unitPrice == null ? 0 : unitPrice) * item.qty();
            totalAmount += itemAmount;
            snapshots.add(new OrderItemSnapshot(
                item.skuId(),
                item.sellerId(),
                offerId,
                item.qty(),
                unitPrice == null ? 0 : unitPrice,
                currency,
                itemAmount,
                Instant.now(),
                currentOffer
            ));
        }

        String shippingSnapshotJson = null;
        if (shippingAddressId != null) {
            Map<String, Object> address = addressRepository.findAddress(shippingAddressId);
            if (address == null) {
                throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "배송지를 찾을 수 없습니다.");
            }
            shippingSnapshotJson = JsonUtils.toJson(objectMapper, address);
        } else if (shippingSnapshot != null && !shippingSnapshot.isEmpty()) {
            shippingSnapshotJson = JsonUtils.toJson(objectMapper, shippingSnapshot);
        }

        String orderNo = generateOrderNo();
        String resolvedShippingMode = resolveShippingMode(shippingMode);
        int shippingFee = "FAST".equals(resolvedShippingMode)
            ? properties.getCart().getFastShippingFee()
            : properties.getCart().getBaseShippingFee();
        int orderTotalAmount = totalAmount + shippingFee;
        String orderCurrency = snapshots.isEmpty() || snapshots.get(0).currency() == null ? "KRW" : snapshots.get(0).currency();
        long orderId = orderRepository.insertOrder(
            userId,
            resolvedCartId,
            OrderStatus.PAYMENT_PENDING.name(),
            orderTotalAmount,
            orderCurrency,
            shippingFee,
            resolvedShippingMode,
            0,
            paymentMethod,
            idempotencyKey,
            shippingSnapshotJson,
            orderNo
        );

        List<OrderRepository.OrderItemInsert> inserts = new ArrayList<>();
        for (OrderItemSnapshot snapshot : snapshots) {
            String priceSnapshotJson = JsonUtils.toJson(objectMapper, snapshot.offerSnapshot());
            inserts.add(new OrderRepository.OrderItemInsert(
                orderId,
                snapshot.skuId(),
                snapshot.sellerId(),
                snapshot.offerId(),
                snapshot.qty(),
                snapshot.unitPrice(),
                snapshot.itemAmount(),
                "ORDERED",
                snapshot.capturedAt(),
                priceSnapshotJson
            ));
        }

        orderRepository.insertOrderItems(inserts);

        // Reserve inventory per item
        for (OrderItemSnapshot snapshot : snapshots) {
            String reserveKey = "order_" + orderId + "_reserve_" + snapshot.skuId();
            inventoryService.reserve(
                snapshot.skuId(),
                snapshot.sellerId(),
                snapshot.qty(),
                reserveKey,
                "ORDER",
                String.valueOf(orderId)
            );
        }

        orderRepository.insertOrderEvent(orderId, "ORDER_CREATED", null, OrderStatus.PAYMENT_PENDING.name(), null, null);
        orderRepository.insertOrderEvent(orderId, "INVENTORY_RESERVED", null, OrderStatus.PAYMENT_PENDING.name(), null, null);

        if (resolvedCartId != null) {
            cartRepository.clearCart(resolvedCartId);
        }

        Map<String, Object> order = orderRepository.findOrderById(orderId);
        return order;
    }

    @Transactional(readOnly = true)
    public Map<String, Object> getOrder(long orderId) {
        Map<String, Object> order = orderRepository.findOrderById(orderId);
        if (order == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "주문 정보를 찾을 수 없습니다.");
        }
        return order;
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listOrders(long userId, Integer limit) {
        int resolvedLimit = limit == null ? DEFAULT_LIST_LIMIT : Math.min(Math.max(limit, 1), 100);
        List<Map<String, Object>> orders = orderRepository.listOrdersByUser(userId, resolvedLimit);
        List<Map<String, Object>> enriched = new ArrayList<>();
        for (Map<String, Object> order : orders) {
            Map<String, Object> mapped = new HashMap<>(order);
            Long orderId = JdbcUtils.asLong(order.get("order_id"));
            if (orderId == null) {
                enriched.add(mapped);
                continue;
            }
            List<Map<String, Object>> items = enrichOrderItems(orderRepository.findOrderItems(orderId));
            mapped.put("item_count", items.size());
            if (!items.isEmpty()) {
                Map<String, Object> primary = items.get(0);
                mapped.put("primary_item_title", JdbcUtils.asString(primary.get("title")));
                mapped.put("primary_item_author", JdbcUtils.asString(primary.get("author")));
                mapped.put("primary_item_material_id", JdbcUtils.asString(primary.get("material_id")));
                mapped.put("primary_item_sku_id", JdbcUtils.asLong(primary.get("sku_id")));
            }
            enriched.add(mapped);
        }
        return enriched;
    }

    @Transactional
    public Map<String, Object> cancelOrder(long userId, long orderId, String reason) {
        Map<String, Object> order = orderRepository.findOrderById(orderId);
        if (order == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "주문 정보를 찾을 수 없습니다.");
        }
        if (JdbcUtils.asLong(order.get("user_id")) != userId) {
            throw new ApiException(HttpStatus.FORBIDDEN, "forbidden", "해당 주문에 접근할 수 없습니다.");
        }
        OrderStatus status = OrderStatus.from(JdbcUtils.asString(order.get("status")));
        if (status == OrderStatus.CANCELED) {
            return order;
        }
        if (!(status == OrderStatus.CREATED || status == OrderStatus.PAYMENT_PENDING)) {
            throw new ApiException(HttpStatus.CONFLICT, "invalid_state", "현재 상태에서는 주문 취소가 불가능합니다.");
        }

        List<Map<String, Object>> items = orderRepository.findOrderItems(orderId);
        for (Map<String, Object> item : items) {
            long skuId = JdbcUtils.asLong(item.get("sku_id"));
            long sellerId = JdbcUtils.asLong(item.get("seller_id"));
            int qty = JdbcUtils.asInt(item.get("qty"));
            long orderItemId = JdbcUtils.asLong(item.get("order_item_id"));
            String releaseKey = "order_" + orderId + "_release_" + orderItemId;
            inventoryService.release(skuId, sellerId, qty, releaseKey, "ORDER", String.valueOf(orderId));
        }

        orderRepository.updateOrderStatus(orderId, OrderStatus.CANCELED.name());
        orderRepository.insertOrderEvent(
            orderId,
            "ORDER_CANCELED",
            status.name(),
            OrderStatus.CANCELED.name(),
            reason,
            null
        );
        return orderRepository.findOrderById(orderId);
    }

    @Transactional
    public void markPaid(long orderId, String paymentId) {
        Map<String, Object> order = orderRepository.findOrderById(orderId);
        if (order == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "주문 정보를 찾을 수 없습니다.");
        }
        OrderStatus status = OrderStatus.from(JdbcUtils.asString(order.get("status")));
        if (status == OrderStatus.PAID) {
            return;
        }
        if (status != OrderStatus.PAYMENT_PENDING) {
            throw new ApiException(HttpStatus.CONFLICT, "invalid_state", "현재 상태에서는 결제를 진행할 수 없습니다.");
        }
        orderRepository.updateOrderStatus(orderId, OrderStatus.PAID.name());
        orderRepository.insertOrderEvent(orderId, "PAYMENT_SUCCEEDED", status.name(), OrderStatus.PAID.name(), null,
            paymentId);
    }

    @Transactional
    public void markReadyToShip(long orderId) {
        transition(orderId, OrderStatus.READY_TO_SHIP, "READY_TO_SHIP");
    }

    @Transactional
    public void markShipped(long orderId) {
        transition(orderId, OrderStatus.SHIPPED, "SHIPPED");
    }

    @Transactional
    public void markDelivered(long orderId) {
        transition(orderId, OrderStatus.DELIVERED, "DELIVERED");
    }

    @Transactional
    public void markRefunded(long orderId, boolean partial) {
        OrderStatus target = partial ? OrderStatus.PARTIALLY_REFUNDED : OrderStatus.REFUNDED;
        transition(orderId, target, "REFUND_SUCCEEDED");
    }

    @Transactional
    public void markRefundPending(long orderId) {
        transition(orderId, OrderStatus.REFUND_PENDING, "REFUND_REQUESTED");
    }

    private void transition(long orderId, OrderStatus target, String eventType) {
        Map<String, Object> order = orderRepository.findOrderById(orderId);
        if (order == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "주문 정보를 찾을 수 없습니다.");
        }
        OrderStatus status = OrderStatus.from(JdbcUtils.asString(order.get("status")));
        if (status == target) {
            return;
        }
        if (!status.canTransitionTo(target)) {
            throw new ApiException(HttpStatus.CONFLICT, "invalid_state", "현재 주문 상태에서는 요청한 처리로 변경할 수 없습니다.");
        }
        orderRepository.updateOrderStatus(orderId, target.name());
        orderRepository.insertOrderEvent(orderId, eventType, status.name(), target.name(), null, null);
    }

    public List<Map<String, Object>> getOrderItems(long orderId) {
        return enrichOrderItems(orderRepository.findOrderItems(orderId));
    }

    public List<Map<String, Object>> getOrderEvents(long orderId) {
        return orderRepository.findOrderEvents(orderId);
    }

    private String generateOrderNo() {
        String date = LocalDate.now().format(DateTimeFormatter.BASIC_ISO_DATE);
        String suffix = UUID.randomUUID().toString().replace("-", "").substring(0, 8).toUpperCase();
        return "ORD" + date + suffix;
    }

    private String resolveShippingMode(String shippingMode) {
        if (shippingMode == null) {
            return "STANDARD";
        }
        String normalized = shippingMode.trim().toUpperCase();
        return "FAST".equals(normalized) ? "FAST" : "STANDARD";
    }

    private List<Map<String, Object>> enrichOrderItems(List<Map<String, Object>> rows) {
        if (rows == null || rows.isEmpty()) {
            return List.of();
        }
        List<Map<String, Object>> enriched = new ArrayList<>();
        for (Map<String, Object> item : rows) {
            Map<String, Object> mapped = new HashMap<>(item);
            mapped.put("captured_at", JdbcUtils.asIsoString(item.get("captured_at")));
            mapped.put("created_at", JdbcUtils.asIsoString(item.get("created_at")));
            mapped.put("unit_price", PriceUtils.normalizeBookPrice(JdbcUtils.asInt(item.get("unit_price"))));
            mapped.put("item_amount", PriceUtils.normalizeBookPrice(JdbcUtils.asInt(item.get("item_amount"))));

            Long skuId = JdbcUtils.asLong(item.get("sku_id"));
            Long sellerId = JdbcUtils.asLong(item.get("seller_id"));
            if (skuId != null && sellerId != null) {
                Map<String, Object> displayInfo = catalogService.getSkuDisplayInfo(skuId, sellerId);
                if (displayInfo != null && !displayInfo.isEmpty()) {
                    mapped.putAll(displayInfo);
                }
            }

            applySnapshotFallback(mapped);
            enriched.add(mapped);
        }
        return enriched;
    }

    private void applySnapshotFallback(Map<String, Object> mapped) {
        String snapshotJson = JdbcUtils.asString(mapped.get("price_snapshot_json"));
        if (snapshotJson == null || snapshotJson.isBlank()) {
            return;
        }
        Map<String, Object> snapshot = parseJsonMap(snapshotJson);
        if (snapshot.isEmpty()) {
            return;
        }

        if (isBlank(mapped.get("title"))) {
            mapped.put("title", firstNonBlank(snapshot, "title", "material_title", "material_label"));
        }
        if (isBlank(mapped.get("author"))) {
            mapped.put("author", firstNonBlank(snapshot, "author", "creator_name"));
        }
        if (isBlank(mapped.get("publisher"))) {
            mapped.put("publisher", firstNonBlank(snapshot, "publisher", "material_publisher"));
        }
        if (isBlank(mapped.get("material_id"))) {
            mapped.put("material_id", firstNonBlank(snapshot, "material_id"));
        }
    }

    private Map<String, Object> parseJsonMap(String json) {
        try {
            return objectMapper.readValue(json, new TypeReference<Map<String, Object>>() {
            });
        } catch (Exception ex) {
            return Collections.emptyMap();
        }
    }

    private String firstNonBlank(Map<String, Object> source, String... keys) {
        if (source == null || keys == null) {
            return null;
        }
        for (String key : keys) {
            String value = JdbcUtils.asString(source.get(key));
            if (!isBlank(value)) {
                return value;
            }
        }
        return null;
    }

    private boolean isBlank(Object value) {
        String text = JdbcUtils.asString(value);
        return text == null || text.isBlank();
    }

    public record OrderItemRequest(Long skuId, Long sellerId, Integer qty, Long offerId, Integer unitPrice) {
    }

    private record OrderItemSnapshot(
        long skuId,
        long sellerId,
        Long offerId,
        int qty,
        int unitPrice,
        String currency,
        int itemAmount,
        Instant capturedAt,
        Map<String, Object> offerSnapshot
    ) {
    }

    public enum OrderStatus {
        CREATED,
        PAYMENT_PENDING,
        PAID,
        READY_TO_SHIP,
        SHIPPED,
        DELIVERED,
        CANCELED,
        REFUND_PENDING,
        REFUNDED,
        PARTIALLY_REFUNDED;

        public static OrderStatus from(String value) {
            if (value == null) {
                return CREATED;
            }
            try {
                return OrderStatus.valueOf(value);
            } catch (IllegalArgumentException ex) {
                return CREATED;
            }
        }

        public boolean canTransitionTo(OrderStatus target) {
            return switch (this) {
                case CREATED -> target == PAYMENT_PENDING || target == CANCELED;
                case PAYMENT_PENDING -> target == PAID || target == CANCELED;
                case PAID -> target == READY_TO_SHIP || target == REFUND_PENDING || target == REFUNDED || target == PARTIALLY_REFUNDED;
                case READY_TO_SHIP -> target == SHIPPED || target == CANCELED || target == REFUND_PENDING;
                case SHIPPED -> target == DELIVERED || target == PARTIALLY_REFUNDED || target == REFUNDED || target == REFUND_PENDING;
                case DELIVERED -> target == PARTIALLY_REFUNDED || target == REFUNDED || target == REFUND_PENDING;
                case REFUND_PENDING -> target == REFUNDED || target == PARTIALLY_REFUNDED;
                case PARTIALLY_REFUNDED -> target == REFUNDED || target == PARTIALLY_REFUNDED || target == REFUND_PENDING;
                default -> false;
            };
        }
    }
}
