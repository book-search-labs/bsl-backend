package com.bsl.checkoutorchestrator.api;

import com.bsl.checkoutorchestrator.service.CheckoutRecoveryService;
import com.bsl.checkoutorchestrator.service.CheckoutSagaService;
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
@RequestMapping(value = "/internal/checkouts", produces = MediaType.APPLICATION_JSON_VALUE)
public class CheckoutController {
    private final CheckoutSagaService checkoutSagaService;
    private final CheckoutRecoveryService checkoutRecoveryService;

    public CheckoutController(CheckoutSagaService checkoutSagaService, CheckoutRecoveryService checkoutRecoveryService) {
        this.checkoutSagaService = checkoutSagaService;
        this.checkoutRecoveryService = checkoutRecoveryService;
    }

    @PostMapping
    public Map<String, Object> startCheckout(
        @RequestBody(required = false) Map<String, Object> request,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return checkoutSagaService.startCheckout(request, traceId, requestId);
    }

    @GetMapping
    public Map<String, Object> listCheckouts(
        @RequestParam(value = "status", required = false) String status,
        @RequestParam(value = "limit", defaultValue = "50") int limit,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return checkoutSagaService.listCheckouts(status, limit, traceId, requestId);
    }

    @GetMapping("/{checkoutId}")
    public Map<String, Object> getCheckout(
        @PathVariable long checkoutId,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return checkoutSagaService.getCheckout(checkoutId, traceId, requestId);
    }

    @PostMapping("/{checkoutId}/steps/{stepName}/retry")
    public Map<String, Object> retryStep(
        @PathVariable long checkoutId,
        @PathVariable String stepName,
        @RequestBody(required = false) Map<String, Object> request,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return checkoutRecoveryService.retryStep(checkoutId, stepName, request, traceId, requestId);
    }

    @PostMapping("/{checkoutId}/steps/{stepName}/reconcile")
    public Map<String, Object> reconcileUnknownStep(
        @PathVariable long checkoutId,
        @PathVariable String stepName,
        @RequestBody(required = false) Map<String, Object> request,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return checkoutRecoveryService.reconcileUnknownStep(checkoutId, stepName, request, traceId, requestId);
    }

    @PostMapping("/{checkoutId}/cancel")
    public Map<String, Object> cancelCheckout(
        @PathVariable long checkoutId,
        @RequestBody(required = false) Map<String, Object> request,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return checkoutRecoveryService.cancelCheckout(checkoutId, request, traceId, requestId);
    }
}
