package com.bsl.ranking.features;

public enum FeatureSource {
    REQUEST,
    KV,
    DERIVED;

    public static FeatureSource from(String raw) {
        if (raw == null) {
            return null;
        }
        return switch (raw.trim().toLowerCase()) {
            case "request" -> REQUEST;
            case "kv", "feature_store", "feature-store" -> KV;
            case "derived" -> DERIVED;
            default -> null;
        };
    }
}
