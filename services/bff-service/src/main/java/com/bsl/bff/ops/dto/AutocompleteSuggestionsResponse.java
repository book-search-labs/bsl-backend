package com.bsl.bff.ops.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class AutocompleteSuggestionsResponse {
    private String version;
    @JsonProperty("trace_id")
    private String traceId;
    @JsonProperty("request_id")
    private String requestId;
    @JsonProperty("took_ms")
    private long tookMs;
    private List<AutocompleteSuggestionDto> suggestions;

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

    public long getTookMs() {
        return tookMs;
    }

    public void setTookMs(long tookMs) {
        this.tookMs = tookMs;
    }

    public List<AutocompleteSuggestionDto> getSuggestions() {
        return suggestions;
    }

    public void setSuggestions(List<AutocompleteSuggestionDto> suggestions) {
        this.suggestions = suggestions;
    }
}
