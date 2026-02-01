package com.bsl.bff.authority.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class AgentAliasResponse {
    private String version;

    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("request_id")
    private String requestId;

    private AgentAliasDto alias;

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

    public AgentAliasDto getAlias() {
        return alias;
    }

    public void setAlias(AgentAliasDto alias) {
        this.alias = alias;
    }
}
