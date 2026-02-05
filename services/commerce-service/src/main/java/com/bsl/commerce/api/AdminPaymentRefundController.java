package com.bsl.commerce.api;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.common.RequestUtils;
import com.bsl.commerce.service.PaymentService;
import com.bsl.commerce.service.RefundService;
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
@RequestMapping("/admin")
public class AdminPaymentRefundController {
    private final PaymentService paymentService;
    private final RefundService refundService;

    public AdminPaymentRefundController(PaymentService paymentService, RefundService refundService) {
        this.paymentService = paymentService;
        this.refundService = refundService;
    }

    @GetMapping("/payments")
    public Map<String, Object> listPayments(@RequestParam(name = "limit", required = false) Integer limit) {
        List<Map<String, Object>> payments = paymentService.listPayments(limit == null ? 50 : limit);
        Map<String, Object> response = base();
        response.put("items", payments);
        response.put("count", payments.size());
        return response;
    }

    @GetMapping("/payments/{paymentId}")
    public Map<String, Object> getPayment(@PathVariable long paymentId) {
        Map<String, Object> payment = paymentService.getPayment(paymentId);
        Map<String, Object> response = base();
        response.put("payment", payment);
        return response;
    }

    @PostMapping("/payments/{paymentId}/cancel")
    public Map<String, Object> cancelPayment(@PathVariable long paymentId, @RequestBody(required = false) CancelRequest request) {
        Map<String, Object> payment = paymentService.cancelPayment(paymentId, request == null ? null : request.reason);
        Map<String, Object> response = base();
        response.put("payment", payment);
        return response;
    }

    @GetMapping("/refunds")
    public Map<String, Object> listRefunds(@RequestParam(name = "limit", required = false) Integer limit) {
        List<Map<String, Object>> refunds = refundService.listRefunds(limit == null ? 50 : limit);
        Map<String, Object> response = base();
        response.put("items", refunds);
        response.put("count", refunds.size());
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

    @PostMapping("/refunds/{refundId}/approve")
    public Map<String, Object> approveRefund(
        @RequestHeader(value = "x-admin-id", required = false) String adminIdHeader,
        @PathVariable long refundId
    ) {
        long adminId = RequestUtils.resolveAdminId(adminIdHeader, 1L);
        Map<String, Object> refund = refundService.approveRefund(refundId, adminId);
        Map<String, Object> response = base();
        response.put("refund", refund);
        return response;
    }

    @PostMapping("/refunds/{refundId}/process")
    public Map<String, Object> processRefund(@PathVariable long refundId, @RequestBody(required = false) RefundProcessRequest request) {
        Map<String, Object> refund = refundService.processRefund(refundId, request == null ? null : request.result);
        Map<String, Object> response = base();
        response.put("refund", refund);
        response.put("items", refundService.listRefundItems(refundId));
        return response;
    }

    @PostMapping("/refunds")
    public Map<String, Object> createRefund(@RequestBody RefundCreateRequest request) {
        if (request == null || request.orderId == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "order_id is required");
        }
        List<RefundService.RefundItemRequest> items = request.items == null ? null : request.items.stream()
            .map(item -> new RefundService.RefundItemRequest(item.orderItemId, item.qty))
            .toList();
        Map<String, Object> refund = refundService.createRefund(request.orderId, items, request.reasonCode,
            request.reasonText, request.idempotencyKey);
        Map<String, Object> response = base();
        response.put("refund", refund);
        response.put("items", refundService.listRefundItems(com.bsl.commerce.common.JdbcUtils.asLong(refund.get("refund_id"))));
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

    public static class CancelRequest {
        public String reason;
    }

    public static class RefundProcessRequest {
        public String result;
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
