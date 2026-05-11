package com.bsl.order.api;

import com.bsl.order.service.OrderService;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(value = "/internal/orders", produces = MediaType.APPLICATION_JSON_VALUE)
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public Map<String, Object> createOrder(
        @RequestBody(required = false) Map<String, Object> request,
        @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return orderService.createOrder(request, idempotencyKey, traceId, requestId);
    }

    @GetMapping("/{orderId}")
    public Map<String, Object> getOrder(
        @PathVariable String orderId,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return orderService.getOrder(orderId, traceId, requestId);
    }
}
