package com.bsl.ranking.features;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "feature-store")
public class FeatureStoreProperties {
    private String path = "config/feature_store.json";
    private long refreshMs = 10000;

    public String getPath() {
        return path;
    }

    public void setPath(String path) {
        this.path = path;
    }

    public long getRefreshMs() {
        return refreshMs;
    }

    public void setRefreshMs(long refreshMs) {
        this.refreshMs = refreshMs;
    }
}
