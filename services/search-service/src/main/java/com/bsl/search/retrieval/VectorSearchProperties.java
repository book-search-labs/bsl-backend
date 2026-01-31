package com.bsl.search.retrieval;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "search.vector")
public class VectorSearchProperties {
    private VectorSearchMode mode = VectorSearchMode.EMBEDDING;
    private String modelId;

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
}
