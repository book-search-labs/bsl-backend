package com.bsl.search.embed;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "embedding")
public class EmbeddingProperties {
    private EmbeddingMode mode = EmbeddingMode.HTTP;
    private String baseUrl;
    private String model;
    private int timeoutMs = 200;
    private int retryCount = 0;
    private Cache cache = new Cache();

    public EmbeddingMode getMode() {
        return mode;
    }

    public void setMode(EmbeddingMode mode) {
        this.mode = mode;
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getModel() {
        return model;
    }

    public void setModel(String model) {
        this.model = model;
    }

    public int getTimeoutMs() {
        return timeoutMs;
    }

    public void setTimeoutMs(int timeoutMs) {
        this.timeoutMs = timeoutMs;
    }

    public int getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }

    public Cache getCache() {
        return cache;
    }

    public void setCache(Cache cache) {
        this.cache = cache;
    }

    public static class Cache {
        private boolean enabled = false;
        private long ttlMs = 60000;
        private int maxEntries = 2000;
        private int maxTextLength = 200;
        private boolean normalize = true;

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
    }
}
