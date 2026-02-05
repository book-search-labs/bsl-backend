package com.bsl.search.retrieval;

import java.util.Locale;

public enum FusionMethod {
    RRF,
    WEIGHTED;

    public static FusionMethod fromString(String value) {
        if (value == null) {
            return null;
        }
        String normalized = value.trim().toLowerCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            return null;
        }
        if (normalized.startsWith("w")) {
            return WEIGHTED;
        }
        if (normalized.contains("rrf")) {
            return RRF;
        }
        return null;
    }
}
