package com.bsl.refund.api;

import com.bsl.refund.common.ResponseSupport;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DummyController {
    @GetMapping("/internal/refunds/_dummy")
    public Map<String, Object> dummy(
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        Map<String, Object> response = ResponseSupport.base("refund-service", traceId, requestId);
        response.put("status", "ready");
        response.put("capability", "refunds");
        return response;
    }
}
