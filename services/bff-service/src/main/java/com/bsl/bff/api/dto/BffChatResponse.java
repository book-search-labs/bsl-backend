package com.bsl.bff.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class BffChatResponse {
    private String version;
    @JsonProperty("trace_id")
    private String traceId;
    @JsonProperty("request_id")
    private String requestId;
    private String status;
    private BffChatMessage answer;
    private List<BffChatSource> sources;
    private List<String> citations;

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

    public BffChatMessage getAnswer() {
        return answer;
    }

    public void setAnswer(BffChatMessage answer) {
        this.answer = answer;
    }

    public List<BffChatSource> getSources() {
        return sources;
    }

    public void setSources(List<BffChatSource> sources) {
        this.sources = sources;
    }

    public List<String> getCitations() {
        return citations;
    }

    public void setCitations(List<String> citations) {
        this.citations = citations;
    }
}
