package com.bsl.bff.ops.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class AutocompleteTrendsResponse {
    private String version;
    @JsonProperty("trace_id")
    private String traceId;
    @JsonProperty("request_id")
    private String requestId;
    private String metric;
    private int count;
    private List<AutocompleteTrendDto> items;

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

    public int getCount() {
        return count;
    }

    public void setCount(int count) {
        this.count = count;
    }

    public List<AutocompleteTrendDto> getItems() {
        return items;
    }

    public void setItems(List<AutocompleteTrendDto> items) {
        this.items = items;
    }
}
