package com.bsl.bff.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class BffChatRequest {
    private String version;
    @JsonProperty("trace_id")
    private String traceId;
    @JsonProperty("request_id")
    private String requestId;
    @JsonProperty("session_id")
    private String sessionId;
    private BffChatMessage message;
    private List<BffChatMessage> history;
    private BffChatOptions options;

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

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }

    public BffChatMessage getMessage() {
        return message;
    }

    public void setMessage(BffChatMessage message) {
        this.message = message;
    }

    public List<BffChatMessage> getHistory() {
        return history;
    }

    public void setHistory(List<BffChatMessage> history) {
        this.history = history;
    }

    public BffChatOptions getOptions() {
        return options;
    }

    public void setOptions(BffChatOptions options) {
        this.options = options;
    }
}
