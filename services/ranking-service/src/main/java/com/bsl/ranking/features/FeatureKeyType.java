package com.bsl.ranking.features;

public enum FeatureKeyType {
    QUERY,
    DOC,
    QUERY_DOC;

    public static FeatureKeyType from(String raw) {
        if (raw == null) {
            return null;
        }
        return switch (raw.trim().toLowerCase()) {
            case "query" -> QUERY;
            case "doc" -> DOC;
            case "query_doc", "query-doc", "querydoc" -> QUERY_DOC;
            default -> null;
        };
    }
}
