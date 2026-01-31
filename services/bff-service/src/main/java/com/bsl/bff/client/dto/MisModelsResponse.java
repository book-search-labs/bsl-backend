package com.bsl.bff.client.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class MisModelsResponse {
    private String version;
    @JsonProperty("trace_id")
    private String traceId;
    @JsonProperty("request_id")
    private String requestId;
    private List<MisModelInfo> models;

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

    public List<MisModelInfo> getModels() {
        return models;
    }

    public void setModels(List<MisModelInfo> models) {
        this.models = models;
    }
}
