package com.bsl.bff.models;

import com.fasterxml.jackson.annotation.JsonProperty;

public class ModelRegistryActionRequest {
    @JsonProperty("model_id")
    private String modelId;
    private String task;
    @JsonProperty("canary_weight")
    private Double canaryWeight;

    public String getModelId() {
        return modelId;
    }

    public void setModelId(String modelId) {
        this.modelId = modelId;
    }

    public String getTask() {
        return task;
    }

    public void setTask(String task) {
        this.task = task;
    }

    public Double getCanaryWeight() {
        return canaryWeight;
    }

    public void setCanaryWeight(Double canaryWeight) {
        this.canaryWeight = canaryWeight;
    }
}
