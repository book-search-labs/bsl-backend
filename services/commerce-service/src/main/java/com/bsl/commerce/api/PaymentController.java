package com.bsl.commerce.api;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.service.PaymentService;
import java.util.HashMap;
import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.http.MediaType;
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
public class PaymentController {
    private final PaymentService paymentService;
    private final Environment environment;

    public PaymentController(PaymentService paymentService, Environment environment) {
        this.paymentService = paymentService;
        this.environment = environment;
    }

    @PostMapping("/payments")
    public Map<String, Object> createPayment(@RequestBody PaymentCreateRequest request) {
        if (request == null || request.orderId == null || request.amount == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "order_id와 amount는 필수입니다.");
        }
        Map<String, Object> payment = paymentService.createPayment(
            request.orderId,
            request.amount,
            request.method,
            request.idempotencyKey,
            request.provider,
            request.returnUrl,
            request.webhookUrl
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
        if (!environment.acceptsProfiles(Profiles.of("dev"))) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "지원하지 않는 엔드포인트입니다.");
        }
        String result = request == null ? "SUCCESS" : request.result;
        Map<String, Object> payment = paymentService.mockComplete(paymentId, result);
        Map<String, Object> response = base();
        response.put("payment", payment);
        return response;
    }

    @PostMapping(value = "/payments/webhook/{provider}", consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> webhook(
        @PathVariable String provider,
        @RequestHeader(name = "X-Signature", required = false) String signature,
        @RequestHeader(name = "X-Event-Id", required = false) String eventIdHeader,
        @RequestParam(name = "event_id", required = false) String eventId,
        @RequestBody(required = false) String rawPayload
    ) {
        String resolvedEventId = firstNonBlank(eventIdHeader, eventId);
        Map<String, Object> webhook = paymentService.handleWebhook(provider, rawPayload, signature, resolvedEventId);
        Map<String, Object> response = base();
        response.putAll(webhook);
        return response;
    }

    private String firstNonBlank(String... values) {
        if (values == null) {
            return null;
        }
        for (String value : values) {
            if (value == null) {
                continue;
            }
            String trimmed = value.trim();
            if (!trimmed.isEmpty()) {
                return trimmed;
            }
        }
        return null;
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
        public String provider;
        public String returnUrl;
        public String webhookUrl;
    }

    public static class PaymentMockRequest {
        public String result;
    }
}
