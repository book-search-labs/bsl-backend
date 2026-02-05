package com.bsl.ranking.features;

import java.util.HashSet;
import java.util.Set;

public final class FeatureSpecValidator {
    private FeatureSpecValidator() {}

    public static void validate(FeatureSpec spec) {
        if (spec == null) {
            throw new IllegalStateException("feature spec missing");
        }
        if (spec.getFeatureSetVersion() == null || spec.getFeatureSetVersion().isBlank()) {
            throw new IllegalStateException("feature_set_version required");
        }
        if (spec.getFeatures().isEmpty()) {
            throw new IllegalStateException("features list empty");
        }

        Set<String> names = new HashSet<>();
        for (FeatureDefinition def : spec.getFeatures()) {
            if (def == null) {
                continue;
            }
            if (def.getName() == null || def.getName().isBlank()) {
                throw new IllegalStateException("feature name required");
            }
            if (!names.add(def.getName())) {
                throw new IllegalStateException("duplicate feature: " + def.getName());
            }
            if (def.getType() == null) {
                throw new IllegalStateException("feature type required: " + def.getName());
            }
            if (def.getKeyType() == null) {
                throw new IllegalStateException("feature key_type required: " + def.getName());
            }
            if (def.getSource() == null) {
                throw new IllegalStateException("feature source required: " + def.getName());
            }
            FeatureTransform transform = def.getTransform();
            if (transform != null && transform.getClipMin() != null && transform.getClipMax() != null) {
                if (transform.getClipMin() > transform.getClipMax()) {
                    throw new IllegalStateException("clip min > max for " + def.getName());
                }
            }
        }
    }
}
