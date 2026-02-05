package com.bsl.bff.ops.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class AutocompleteSuggestionUpdateResponse {
    private String version;
    @JsonProperty("trace_id")
    private String traceId;
    @JsonProperty("request_id")
    private String requestId;
    private AutocompleteSuggestionDto suggestion;

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

    public AutocompleteSuggestionDto getSuggestion() {
        return suggestion;
    }

    public void setSuggestion(AutocompleteSuggestionDto suggestion) {
        this.suggestion = suggestion;
    }
}
