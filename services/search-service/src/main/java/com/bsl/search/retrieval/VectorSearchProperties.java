package com.bsl.search.retrieval;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "search.vector")
public class VectorSearchProperties {
    private VectorSearchMode mode = VectorSearchMode.EMBEDDING;
    private String modelId;
    private Cache cache = new Cache();
    private Promotion promotion = new Promotion();

    public VectorSearchMode getMode() {
        return mode;
    }

    public void setMode(VectorSearchMode mode) {
        this.mode = mode;
    }

    public String getModelId() {
        return modelId;
    }

    public void setModelId(String modelId) {
        this.modelId = modelId;
    }

    public Cache getCache() {
        return cache;
    }

    public void setCache(Cache cache) {
        this.cache = cache;
    }

    public Promotion getPromotion() {
        return promotion;
    }

    public void setPromotion(Promotion promotion) {
        this.promotion = promotion;
    }

    public static class Cache {
        private boolean enabled = false;
        private long ttlMs = 20000;
        private int maxEntries = 2000;
        private int maxTextLength = 200;
        private boolean normalize = true;
        private boolean cacheDebug = false;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public long getTtlMs() {
            return ttlMs;
        }

        public void setTtlMs(long ttlMs) {
            this.ttlMs = ttlMs;
        }

        public int getMaxEntries() {
            return maxEntries;
        }

        public void setMaxEntries(int maxEntries) {
            this.maxEntries = maxEntries;
        }

        public int getMaxTextLength() {
            return maxTextLength;
        }

        public void setMaxTextLength(int maxTextLength) {
            this.maxTextLength = maxTextLength;
        }

        public boolean isNormalize() {
            return normalize;
        }

        public void setNormalize(boolean normalize) {
            this.normalize = normalize;
        }

        public boolean isCacheDebug() {
            return cacheDebug;
        }

        public void setCacheDebug(boolean cacheDebug) {
            this.cacheDebug = cacheDebug;
        }
    }

    public static class Promotion {
        private boolean enabled = false;
        private String separators = "#,::";

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getSeparators() {
            return separators;
        }

        public void setSeparators(String separators) {
            this.separators = separators;
        }
    }
}
