package com.bsl.autocomplete.api;

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
}
