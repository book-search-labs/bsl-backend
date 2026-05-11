package com.bsl.payment.common;

import com.fasterxml.jackson.annotation.JsonProperty;

public record ErrorResponse(
    ErrorDetail error,
    @JsonProperty("trace_id") String traceId,
    @JsonProperty("request_id") String requestId
) {
    public record ErrorDetail(String code, String message) {
    }
}

