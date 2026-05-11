package com.bsl.refund.common;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

public final class ResponseSupport {
    private ResponseSupport() {
    }

    public static Map<String, Object> base(String service, String traceId, String requestId) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("version", "v1");
        response.put("service", service);
        response.put("trace_id", resolve(traceId));
        response.put("request_id", resolve(requestId));
        return response;
    }

    private static String resolve(String value) {
        return value == null || value.isBlank() ? UUID.randomUUID().toString() : value;
    }
}
