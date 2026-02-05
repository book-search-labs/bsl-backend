package com.bsl.outboxrelay.api;

import com.bsl.outboxrelay.relay.OutboxRelayService;
import java.util.HashMap;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {
    private final OutboxRelayService relayService;

    public HealthController(OutboxRelayService relayService) {
        this.relayService = relayService;
    }

    @GetMapping("/health")
    public Map<String, Object> health() {
        Map<String, Object> response = new HashMap<>();
        response.put("status", "ok");
        response.put("last_run_at_ms", relayService.getLastRunAt());
        if (relayService.getLastError() != null) {
            response.put("last_error", relayService.getLastError());
        }
        return response;
    }
}
