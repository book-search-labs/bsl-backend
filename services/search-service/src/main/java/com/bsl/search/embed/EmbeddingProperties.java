package com.bsl.search.embed;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "embedding")
public class EmbeddingProperties {
    private EmbeddingMode mode = EmbeddingMode.TOY;
    private String baseUrl;
    private String model;
    private int timeoutMs = 200;

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
}
