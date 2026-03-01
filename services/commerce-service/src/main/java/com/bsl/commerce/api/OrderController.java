package com.bsl.commerce.api;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.common.RequestUtils;
import com.bsl.commerce.service.OrderService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/orders")
    public Map<String, Object> createOrder(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @RequestBody OrderCreateRequest request
    ) {
        if (request == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "요청 본문이 필요합니다.");
        }
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<OrderService.OrderItemRequest> items = request.items == null ? null : request.items.stream()
            .map(item -> new OrderService.OrderItemRequest(item.skuId, item.sellerId, item.qty, item.offerId, item.unitPrice))
            .toList();

        Map<String, Object> order = orderService.createOrder(
            userId,
            request.cartId,
            items,
            request.shippingAddressId,
            request.shippingSnapshot,
            request.shippingMode,
            request.paymentMethod,
            request.idempotencyKey
        );
        Map<String, Object> response = base();
        response.put("order", order);
        response.put("items", orderService.getOrderItems(JdbcUtils.asLong(order.get("order_id"))));
        response.put("events", orderService.getOrderEvents(JdbcUtils.asLong(order.get("order_id"))));
        return response;
    }

    @GetMapping("/orders/{orderId}")
    public Map<String, Object> getOrder(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @PathVariable long orderId
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> order = orderService.getOrder(orderId);
        if (JdbcUtils.asLong(order.get("user_id")) != userId) {
            throw new ApiException(HttpStatus.FORBIDDEN, "forbidden", "해당 주문에 접근할 수 없습니다.");
        }
        Map<String, Object> response = base();
        response.put("order", order);
        response.put("items", orderService.getOrderItems(orderId));
        response.put("events", orderService.getOrderEvents(orderId));
        return response;
    }

    @GetMapping("/orders")
    public Map<String, Object> listOrders(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @RequestParam(name = "limit", required = false) Integer limit
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> orders = orderService.listOrders(userId, limit);
        Map<String, Object> response = base();
        response.put("items", orders);
        response.put("count", orders.size());
        return response;
    }

    @PostMapping("/orders/{orderId}/cancel")
    public Map<String, Object> cancelOrder(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @PathVariable long orderId,
        @RequestBody(required = false) CancelRequest request
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> order = orderService.cancelOrder(userId, orderId, request == null ? null : request.reason);
        Map<String, Object> response = base();
        response.put("order", order);
        response.put("items", orderService.getOrderItems(orderId));
        response.put("events", orderService.getOrderEvents(orderId));
        return response;
    }

    private Map<String, Object> base() {
        RequestContext context = RequestContextHolder.get();
        Map<String, Object> response = new HashMap<>();
        response.put("version", "v1");
        response.put("trace_id", context == null ? null : context.getTraceId());
        response.put("request_id", context == null ? null : context.getRequestId());
        return response;
    }

    public static class OrderCreateRequest {
        public Long cartId;
        public List<OrderItemRequest> items;
        public Long shippingAddressId;
        public Map<String, Object> shippingSnapshot;
        public String shippingMode;
        public String paymentMethod;
        public String idempotencyKey;
    }

    public static class OrderItemRequest {
        public Long skuId;
        public Long sellerId;
        public Integer qty;
        public Long offerId;
        public Integer unitPrice;
    }

    public static class CancelRequest {
        public String reason;
    }
}
