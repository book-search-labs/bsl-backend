package com.bsl.payment.api;

import com.bsl.payment.service.PaymentService;
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
@RequestMapping(value = "/internal/payments", produces = MediaType.APPLICATION_JSON_VALUE)
public class PaymentController {
    private final PaymentService paymentService;

    public PaymentController(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @PostMapping("/authorize")
    public Map<String, Object> authorize(
        @RequestBody(required = false) Map<String, Object> request,
        @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return paymentService.authorize(request, idempotencyKey, traceId, requestId);
    }

    @PostMapping("/cancel")
    public Map<String, Object> cancel(
        @RequestBody(required = false) Map<String, Object> request,
        @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return paymentService.cancel(request, idempotencyKey, traceId, requestId);
    }

    @GetMapping("/by-idempotency-key/{idempotencyKey}")
    public Map<String, Object> findByIdempotencyKey(@PathVariable String idempotencyKey) {
        return paymentService.findByIdempotencyKey(idempotencyKey);
    }
}
