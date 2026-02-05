package com.bsl.bff.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class BffAckResponse {
    private String version;
    @JsonProperty("trace_id")
    private String traceId;
    @JsonProperty("request_id")
    private String requestId;
    private String status;

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

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
