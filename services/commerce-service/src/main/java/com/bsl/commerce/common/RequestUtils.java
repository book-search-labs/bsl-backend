package com.bsl.commerce.common;

import org.springframework.http.HttpStatus;

public final class RequestUtils {
    private RequestUtils() {
    }

    public static long requireLong(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + " is required");
        }
        try {
            return Long.parseLong(value.trim());
        } catch (NumberFormatException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + " must be a number");
        }
    }

    public static long resolveUserId(String headerValue, long defaultId) {
        if (headerValue == null || headerValue.isBlank()) {
            return defaultId;
        }
        try {
            return Long.parseLong(headerValue.trim());
        } catch (NumberFormatException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "x-user-id must be numeric");
        }
    }

    public static long resolveAdminId(String headerValue, long defaultId) {
        if (headerValue == null || headerValue.isBlank()) {
            return defaultId;
        }
        try {
            return Long.parseLong(headerValue.trim());
        } catch (NumberFormatException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "x-admin-id must be numeric");
        }
    }
}
