package com.bsl.checkoutorchestrator.api;

import com.bsl.checkoutorchestrator.common.ResponseSupport;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {
    @GetMapping("/health")
    public Map<String, Object> health(
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        Map<String, Object> response = ResponseSupport.base("checkout-orchestrator-service", traceId, requestId);
        response.put("status", "ok");
        return response;
    }
}
