package com.bsl.bff.models;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.ArrayList;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class ModelRegistrySnapshot {
    @JsonProperty("updated_at")
    private String updatedAt;
    private List<ModelRegistryEntry> models = new ArrayList<>();

    public String getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(String updatedAt) {
        this.updatedAt = updatedAt;
    }

    public List<ModelRegistryEntry> getModels() {
        return models;
    }

    public void setModels(List<ModelRegistryEntry> models) {
        this.models = models;
    }
}
