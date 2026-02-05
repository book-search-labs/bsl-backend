package com.bsl.ranking.api;

import jakarta.servlet.http.HttpServletRequest;
import java.util.UUID;

public final class RequestIdUtil {
    private RequestIdUtil() {
    }

    public static String resolveOrGenerate(String value) {
        if (value != null && !value.trim().isEmpty()) {
            return value;
        }
        return UUID.randomUUID().toString();
    }

    public static String resolveOrGenerate(HttpServletRequest request, String headerName) {
        String value = request.getHeader(headerName);
        return resolveOrGenerate(value);
    }
}
