package com.bsl.commerce.api;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.service.PaymentService;
import java.util.HashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class PaymentController {
    private final PaymentService paymentService;

    public PaymentController(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @PostMapping("/payments")
    public Map<String, Object> createPayment(@RequestBody PaymentCreateRequest request) {
        if (request == null || request.orderId == null || request.amount == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "order_id and amount are required");
        }
        Map<String, Object> payment = paymentService.createPayment(
            request.orderId,
            request.amount,
            request.method,
            request.idempotencyKey
        );
        Map<String, Object> response = base();
        response.put("payment", payment);
        return response;
    }

    @GetMapping("/payments/{paymentId}")
    public Map<String, Object> getPayment(@PathVariable long paymentId) {
        Map<String, Object> payment = paymentService.getPayment(paymentId);
        Map<String, Object> response = base();
        response.put("payment", payment);
        return response;
    }

    @PostMapping("/payments/{paymentId}/mock/complete")
    public Map<String, Object> mockComplete(@PathVariable long paymentId, @RequestBody PaymentMockRequest request) {
        String result = request == null ? "SUCCESS" : request.result;
        Map<String, Object> payment = paymentService.mockComplete(paymentId, result);
        Map<String, Object> response = base();
        response.put("payment", payment);
        return response;
    }

    @PostMapping("/payments/webhook/{provider}")
    public Map<String, Object> webhook(
        @PathVariable String provider,
        @RequestParam(name = "event_id", required = false) String eventId,
        @RequestBody(required = false) Map<String, Object> payload
    ) {
        paymentService.handleWebhook(provider, payload, eventId);
        Map<String, Object> response = base();
        response.put("status", "ok");
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

    public static class PaymentCreateRequest {
        public Long orderId;
        public Integer amount;
        public String method;
        public String idempotencyKey;
    }

    public static class PaymentMockRequest {
        public String result;
    }
}
