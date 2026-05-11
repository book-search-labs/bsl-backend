package com.bsl.order.api;

import com.bsl.order.common.ResponseSupport;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DummyController {
    @GetMapping("/internal/orders/_dummy")
    public Map<String, Object> dummy(
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        Map<String, Object> response = ResponseSupport.base("order-service", traceId, requestId);
        response.put("status", "ready");
        response.put("capability", "orders");
        return response;
    }
}
