package com.bsl.bff.models;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class ModelRegistryEntry {
    @JsonProperty("id")
    private String id;
    private String task;
    private String backend;
    @JsonProperty("artifact_uri")
    private String artifactUri;
    private Boolean active;
    private Boolean canary;
    @JsonProperty("canary_weight")
    private Double canaryWeight;
    private String status;
    @JsonProperty("updated_at")
    private String updatedAt;
    @JsonProperty("input_name")
    private String inputName;
    @JsonProperty("output_name")
    private String outputName;
    @JsonProperty("feature_order")
    private List<String> featureOrder;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getTask() {
        return task;
    }

    public void setTask(String task) {
        this.task = task;
    }

    public String getBackend() {
        return backend;
    }

    public void setBackend(String backend) {
        this.backend = backend;
    }

    public String getArtifactUri() {
        return artifactUri;
    }

    public void setArtifactUri(String artifactUri) {
        this.artifactUri = artifactUri;
    }

    public Boolean getActive() {
        return active;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }

    public Boolean getCanary() {
        return canary;
    }

    public void setCanary(Boolean canary) {
        this.canary = canary;
    }

    public Double getCanaryWeight() {
        return canaryWeight;
    }

    public void setCanaryWeight(Double canaryWeight) {
        this.canaryWeight = canaryWeight;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(String updatedAt) {
        this.updatedAt = updatedAt;
    }

    public String getInputName() {
        return inputName;
    }

    public void setInputName(String inputName) {
        this.inputName = inputName;
    }

    public String getOutputName() {
        return outputName;
    }

    public void setOutputName(String outputName) {
        this.outputName = outputName;
    }

    public List<String> getFeatureOrder() {
        return featureOrder;
    }

    public void setFeatureOrder(List<String> featureOrder) {
        this.featureOrder = featureOrder;
    }
}
