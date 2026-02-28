package com.bsl.bff.ops;

import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.ops.dto.MetricsSummaryResponse;
import com.bsl.bff.ops.dto.MetricsTimeseriesResponse;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/admin/ops/metrics")
public class MetricsOpsController {
    private final MetricsOpsRepository repository;

    public MetricsOpsController(MetricsOpsRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/summary")
    public MetricsSummaryResponse summary(
        @RequestParam(value = "window", required = false) String window
    ) {
        if (!repository.isEnabled()) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "metrics_disabled", "metrics endpoint disabled");
        }
        RequestContext context = RequestContextHolder.get();
        try {
            MetricsSummaryResponse response = new MetricsSummaryResponse();
            response.setVersion("v1");
            response.setTraceId(context == null ? null : context.getTraceId());
            response.setRequestId(context == null ? null : context.getRequestId());
            response.setSummary(repository.fetchSummary(window));
            return response;
        } catch (IllegalStateException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "metrics_unavailable", ex.getMessage());
        }
    }

    @GetMapping("/timeseries")
    public MetricsTimeseriesResponse timeseries(
        @RequestParam(value = "metric", required = false) String metric,
        @RequestParam(value = "window", required = false) String window
    ) {
        if (!repository.isEnabled()) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "metrics_disabled", "metrics endpoint disabled");
        }
        RequestContext context = RequestContextHolder.get();
        try {
            MetricsTimeseriesResponse response = new MetricsTimeseriesResponse();
            response.setVersion("v1");
            response.setTraceId(context == null ? null : context.getTraceId());
            response.setRequestId(context == null ? null : context.getRequestId());
            response.setMetric(repository.normalizeMetric(metric));
            response.setItems(repository.fetchTimeseries(metric, window));
            return response;
        } catch (IllegalStateException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "metrics_unavailable", ex.getMessage());
        }
    }
}
