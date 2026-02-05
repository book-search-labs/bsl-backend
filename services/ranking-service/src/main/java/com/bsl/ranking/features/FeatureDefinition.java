package com.bsl.ranking.features;

public class FeatureDefinition {
    private final String name;
    private final FeatureType type;
    private final FeatureKeyType keyType;
    private final FeatureSource source;
    private final FeatureTransform transform;

    public FeatureDefinition(
        String name,
        FeatureType type,
        FeatureKeyType keyType,
        FeatureSource source,
        FeatureTransform transform
    ) {
        this.name = name;
        this.type = type;
        this.keyType = keyType;
        this.source = source;
        this.transform = transform;
    }

    public String getName() {
        return name;
    }

    public FeatureType getType() {
        return type;
    }

    public FeatureKeyType getKeyType() {
        return keyType;
    }

    public FeatureSource getSource() {
        return source;
    }

    public FeatureTransform getTransform() {
        return transform;
    }
}
