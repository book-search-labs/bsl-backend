package com.bsl.ranking.features;

public enum FeatureType {
    FLOAT,
    INT,
    BOOL,
    CATEGORICAL;

    public static FeatureType from(String raw) {
        if (raw == null) {
            return null;
        }
        return switch (raw.trim().toLowerCase()) {
            case "float" -> FLOAT;
            case "int", "integer" -> INT;
            case "bool", "boolean" -> BOOL;
            case "categorical", "category" -> CATEGORICAL;
            default -> null;
        };
    }
}
