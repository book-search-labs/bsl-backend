package com.bsl.commerce.common;

import java.security.SecureRandom;
import java.util.Locale;
import java.util.UUID;

public final class IdGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int TRACE_ID_BYTES = 16;
    private static final int SPAN_ID_BYTES = 8;

    private IdGenerator() {
    }

    public static String resolveRequestId(String headerValue) {
        if (headerValue != null && !headerValue.isBlank()) {
            return headerValue.trim();
        }
        return "req_" + UUID.randomUUID().toString().replace("-", "");
    }

    public static String resolveTraceId(String headerValue) {
        return resolveTraceId(headerValue, null);
    }

    public static String resolveTraceId(String headerValue, String traceparent) {
        String normalizedHeader = normalizeTraceId(headerValue);
        if (normalizedHeader != null) {
            return normalizedHeader;
        }
        String fromTraceparent = extractTraceId(traceparent);
        if (fromTraceparent != null) {
            return fromTraceparent;
        }
        return randomHex(TRACE_ID_BYTES);
    }

    public static String resolveTraceparent(String traceparent, String traceId) {
        String extracted = extractTraceId(traceparent);
        if (extracted != null) {
            return traceparent;
        }
        String resolvedTraceId = traceId == null ? randomHex(TRACE_ID_BYTES) : traceId;
        return "00-" + resolvedTraceId + "-" + randomHex(SPAN_ID_BYTES) + "-01";
    }

    private static String normalizeTraceId(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String trimmed = value.trim();
        if (trimmed.startsWith("trace_")) {
            trimmed = trimmed.substring("trace_".length());
        }
        if (isValidTraceId(trimmed)) {
            return trimmed.toLowerCase(Locale.ROOT);
        }
        return null;
    }

    private static String extractTraceId(String traceparent) {
        if (traceparent == null || traceparent.isBlank()) {
            return null;
        }
        String[] parts = traceparent.trim().split("-");
        if (parts.length != 4) {
            return null;
        }
        String traceId = parts[1];
        return isValidTraceId(traceId) ? traceId.toLowerCase(Locale.ROOT) : null;
    }

    private static boolean isValidTraceId(String value) {
        if (value == null || value.length() != 32) {
            return false;
        }
        if (value.chars().allMatch(ch -> ch == '0')) {
            return false;
        }
        return value.chars().allMatch(ch -> Character.digit(ch, 16) >= 0);
    }

    private static String randomHex(int bytes) {
        byte[] buffer = new byte[bytes];
        RANDOM.nextBytes(buffer);
        StringBuilder sb = new StringBuilder(bytes * 2);
        for (byte b : buffer) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }
}
