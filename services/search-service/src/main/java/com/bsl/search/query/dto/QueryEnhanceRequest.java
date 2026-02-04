package com.bsl.search.query.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;

public class QueryEnhanceRequest {
    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("request_id")
    private String requestId;

    @JsonProperty("q_norm")
    private String qNorm;

    @JsonProperty("q_nospace")
    private String qNospace;

    private String reason;
    private Map<String, Object> signals;
    private Map<String, Object> detected;
    private String locale;
    private Boolean debug;

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

    public String getQNorm() {
        return qNorm;
    }

    public void setQNorm(String qNorm) {
        this.qNorm = qNorm;
    }

    public String getQNospace() {
        return qNospace;
    }

    public void setQNospace(String qNospace) {
        this.qNospace = qNospace;
    }

    public String getReason() {
        return reason;
    }

    public void setReason(String reason) {
        this.reason = reason;
    }

    public Map<String, Object> getSignals() {
        return signals;
    }

    public void setSignals(Map<String, Object> signals) {
        this.signals = signals;
    }

    public Map<String, Object> getDetected() {
        return detected;
    }

    public void setDetected(Map<String, Object> detected) {
        this.detected = detected;
    }

    public String getLocale() {
        return locale;
    }

    public void setLocale(String locale) {
        this.locale = locale;
    }

    public Boolean getDebug() {
        return debug;
    }

    public void setDebug(Boolean debug) {
        this.debug = debug;
    }
}
