package com.bsl.inventory.api;

import com.bsl.inventory.common.ResponseSupport;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DummyController {
    @GetMapping("/internal/inventory/_dummy")
    public Map<String, Object> dummy(
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        Map<String, Object> response = ResponseSupport.base("inventory-service", traceId, requestId);
        response.put("status", "ready");
        response.put("capability", "inventory");
        return response;
    }
}
