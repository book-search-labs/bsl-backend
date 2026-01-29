package com.bsl.bff.api;

import com.bsl.bff.api.dto.BffHealthResponse;
import com.bsl.bff.client.ReadyCheckService;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {
    private final ReadyCheckService readyCheckService;

    public HealthController(ReadyCheckService readyCheckService) {
        this.readyCheckService = readyCheckService;
    }

    @GetMapping("/health")
    public BffHealthResponse health() {
        RequestContext context = RequestContextHolder.get();
        BffHealthResponse response = new BffHealthResponse();
        response.setStatus("ok");
        if (context != null) {
            response.setTraceId(context.getTraceId());
            response.setRequestId(context.getRequestId());
        }
        return response;
    }

    @GetMapping("/ready")
    public BffHealthResponse ready() {
        RequestContext context = RequestContextHolder.get();
        Map<String, String> downstream = readyCheckService.check(context);
        BffHealthResponse response = new BffHealthResponse();
        response.setStatus(downstream.values().stream().allMatch("ok"::equals) ? "ok" : "degraded");
        response.setDownstream(downstream);
        if (context != null) {
            response.setTraceId(context.getTraceId());
            response.setRequestId(context.getRequestId());
        }
        return response;
    }
}
