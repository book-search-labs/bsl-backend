package com.bsl.shipment.api;

import com.bsl.shipment.common.ResponseSupport;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DummyController {
    @GetMapping("/internal/shipments/_dummy")
    public Map<String, Object> dummy(
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        Map<String, Object> response = ResponseSupport.base("shipment-service", traceId, requestId);
        response.put("status", "ready");
        response.put("capability", "shipments");
        return response;
    }
}
