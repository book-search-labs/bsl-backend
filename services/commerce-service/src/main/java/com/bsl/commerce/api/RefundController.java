package com.bsl.commerce.api;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.service.RefundService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class RefundController {
    private final RefundService refundService;

    public RefundController(RefundService refundService) {
        this.refundService = refundService;
    }

    @PostMapping("/refunds")
    public Map<String, Object> createRefund(@RequestBody RefundCreateRequest request) {
        if (request == null || request.orderId == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "order_id is required");
        }
        List<RefundService.RefundItemRequest> items = request.items == null ? null : request.items.stream()
            .map(item -> new RefundService.RefundItemRequest(item.orderItemId, item.qty))
            .toList();
        Map<String, Object> refund = refundService.createRefund(
            request.orderId,
            items,
            request.reasonCode,
            request.reasonText,
            request.idempotencyKey
        );
        long refundId = com.bsl.commerce.common.JdbcUtils.asLong(refund.get("refund_id"));
        Map<String, Object> response = base();
        response.put("refund", refund);
        response.put("items", refundService.listRefundItems(refundId));
        return response;
    }


    @GetMapping("/refunds/{refundId}")
    public Map<String, Object> getRefund(@PathVariable long refundId) {
        Map<String, Object> refund = refundService.getRefund(refundId);
        Map<String, Object> response = base();
        response.put("refund", refund);
        response.put("items", refundService.listRefundItems(refundId));
        return response;
    }

    @GetMapping("/refunds/by-order/{orderId}")
    public Map<String, Object> listByOrder(@PathVariable long orderId) {
        List<Map<String, Object>> refunds = refundService.listRefundsByOrder(orderId);
        Map<String, Object> response = base();
        response.put("items", refunds);
        response.put("count", refunds.size());
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

    public static class RefundCreateRequest {
        public Long orderId;
        public List<RefundItemRequest> items;
        public String reasonCode;
        public String reasonText;
        public String idempotencyKey;
    }

    public static class RefundItemRequest {
        public long orderItemId;
        public int qty;
    }

}
