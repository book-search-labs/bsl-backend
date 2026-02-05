package com.bsl.commerce.common;

public class RequestContext {
    private final String requestId;
    private final String traceId;
    private final String traceparent;
    private final long startedAtNs;

    public RequestContext(String requestId, String traceId, String traceparent, long startedAtNs) {
        this.requestId = requestId;
        this.traceId = traceId;
        this.traceparent = traceparent;
        this.startedAtNs = startedAtNs;
    }

    public String getRequestId() {
        return requestId;
    }

    public String getTraceId() {
        return traceId;
    }

    public String getTraceparent() {
        return traceparent;
    }

    public long getStartedAtNs() {
        return startedAtNs;
    }
}
