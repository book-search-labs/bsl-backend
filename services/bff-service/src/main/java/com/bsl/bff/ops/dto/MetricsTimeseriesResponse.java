package com.bsl.bff.ops.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class MetricsTimeseriesResponse {
    private String version;

    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("request_id")
    private String requestId;

    private String metric;
    private List<MetricsPointDto> items;

    public String getVersion() {
        return version;
    }

    public void setVersion(String version) {
        this.version = version;
    }

    public String getTraceId() {
        return traceId;
    }

    public void setTraceId(String traceId) {
        this.traceId = traceId;
    }

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }

    public String getMetric() {
        return metric;
    }

    public void setMetric(String metric) {
        this.metric = metric;
    }

    public List<MetricsPointDto> getItems() {
        return items;
    }

    public void setItems(List<MetricsPointDto> items) {
        this.items = items;
    }
}
