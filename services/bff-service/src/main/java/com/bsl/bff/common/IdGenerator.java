package com.bsl.bff.common;

import java.util.UUID;

public final class IdGenerator {
    private IdGenerator() {
    }

    public static String resolveRequestId(String headerValue) {
        if (headerValue != null && !headerValue.isBlank()) {
            return headerValue.trim();
        }
        return "req_" + UUID.randomUUID().toString().replace("-", "");
    }

    public static String resolveTraceId(String headerValue) {
        if (headerValue != null && !headerValue.isBlank()) {
            return headerValue.trim();
        }
        return "trace_" + UUID.randomUUID().toString().replace("-", "");
    }
}
