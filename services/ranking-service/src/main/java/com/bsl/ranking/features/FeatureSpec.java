package com.bsl.ranking.features;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class FeatureSpec {
    private final String version;
    private final String featureSetVersion;
    private final List<FeatureDefinition> features;
    private final Map<String, FeatureDefinition> byName;

    public FeatureSpec(String version, String featureSetVersion, List<FeatureDefinition> features) {
        this.version = version;
        this.featureSetVersion = featureSetVersion;
        this.features = features == null ? List.of() : List.copyOf(features);
        Map<String, FeatureDefinition> map = new LinkedHashMap<>();
        for (FeatureDefinition def : this.features) {
            if (def != null && def.getName() != null) {
                map.put(def.getName(), def);
            }
        }
        this.byName = Collections.unmodifiableMap(map);
    }

    public String getVersion() {
        return version;
    }

    public String getFeatureSetVersion() {
        return featureSetVersion;
    }

    public List<FeatureDefinition> getFeatures() {
        return features;
    }

    public FeatureDefinition get(String name) {
        return byName.get(name);
    }

    public Map<String, FeatureDefinition> asMap() {
        return byName;
    }
}
