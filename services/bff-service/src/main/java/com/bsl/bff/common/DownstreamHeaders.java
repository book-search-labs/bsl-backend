package com.bsl.bff.common;

import org.springframework.http.HttpHeaders;

public final class DownstreamHeaders {
    private DownstreamHeaders() {
    }

    public static HttpHeaders from(RequestContext context) {
        HttpHeaders headers = new HttpHeaders();
        if (context == null) {
            return headers;
        }
        if (context.getRequestId() != null) {
            headers.add("x-request-id", context.getRequestId());
        }
        if (context.getTraceId() != null) {
            headers.add("x-trace-id", context.getTraceId());
        }
        if (context.getTraceparent() != null && !context.getTraceparent().isBlank()) {
            headers.add("traceparent", context.getTraceparent());
        }
        return headers;
    }
}
