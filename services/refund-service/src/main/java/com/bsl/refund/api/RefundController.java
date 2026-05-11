package com.bsl.refund.api;

import com.bsl.refund.service.RefundService;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(produces = MediaType.APPLICATION_JSON_VALUE)
public class RefundController {
    private final RefundService refundService;

    public RefundController(RefundService refundService) {
        this.refundService = refundService;
    }

    @PostMapping({"/internal/refunds", "/api/v1/refunds", "/admin/refunds"})
    public Map<String, Object> create(
        @RequestBody(required = false) Map<String, Object> request,
        @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return refundService.create(request, idempotencyKey, traceId, requestId);
    }

    @GetMapping({"/internal/refunds/{refundId}", "/api/v1/refunds/{refundId}", "/admin/refunds/{refundId}"})
    public Map<String, Object> get(
        @PathVariable String refundId,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return refundService.get(refundId, traceId, requestId);
    }

    @GetMapping({"/internal/refunds/by-order/{orderId}", "/api/v1/refunds/by-order/{orderId}"})
    public Map<String, Object> byOrder(
        @PathVariable String orderId,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return refundService.listByOrder(orderId, traceId, requestId);
    }

    @GetMapping("/admin/refunds")
    public Map<String, Object> list(
        @RequestParam(value = "orderId", required = false) String orderId,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return refundService.list(orderId, traceId, requestId);
    }

    @PostMapping({"/internal/refunds/{refundId}/approve", "/admin/refunds/{refundId}/approve"})
    public Map<String, Object> approve(
        @PathVariable String refundId,
        @RequestBody(required = false) Map<String, Object> request,
        @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return refundService.approve(refundId, request, idempotencyKey, traceId, requestId);
    }

    @PostMapping({"/internal/refunds/{refundId}/process", "/admin/refunds/{refundId}/process"})
    public Map<String, Object> process(
        @PathVariable String refundId,
        @RequestBody(required = false) Map<String, Object> request,
        @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return refundService.process(refundId, request, idempotencyKey, traceId, requestId);
    }
}
