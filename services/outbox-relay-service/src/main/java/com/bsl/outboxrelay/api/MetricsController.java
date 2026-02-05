package com.bsl.outboxrelay.api;

import com.bsl.outboxrelay.outbox.OutboxEventRepository;
import com.bsl.outboxrelay.relay.OutboxRelayMetrics;
import com.bsl.outboxrelay.relay.OutboxRelayService;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MetricsController {
    private final OutboxEventRepository repository;
    private final OutboxRelayService relayService;

    public MetricsController(OutboxEventRepository repository, OutboxRelayService relayService) {
        this.repository = repository;
        this.relayService = relayService;
    }

    @GetMapping("/metrics")
    public Map<String, Object> metrics() {
        Map<String, Object> response = new HashMap<>();
        long newCount = repository.countByStatus("NEW");
        long failedCount = repository.countByStatus("FAILED");
        response.put("outbox_new_count", newCount);
        response.put("outbox_failed_count", failedCount);

        OutboxRelayMetrics metrics = relayService.getMetrics();
        response.put("outbox_publish_success_total", metrics.getPublishSuccess());
        response.put("outbox_publish_failure_total", metrics.getPublishFailure());
        response.put("outbox_publish_total", metrics.getPublishTotal());

        Instant oldest = repository.minCreatedAtForStatus("NEW");
        long lagSeconds = 0;
        if (oldest != null) {
            lagSeconds = Math.max(0, Duration.between(oldest, Instant.now()).getSeconds());
        }
        response.put("outbox_relay_lag_seconds", lagSeconds);
        return response;
    }
}
