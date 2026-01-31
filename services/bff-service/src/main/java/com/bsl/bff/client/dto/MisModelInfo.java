package com.bsl.bff.client.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class MisModelInfo {
    private String id;
    private String task;
    private String status;
    private String backend;
    private Boolean active;
    private Boolean canary;
    @JsonProperty("canary_weight")
    private Double canaryWeight;
    @JsonProperty("artifact_uri")
    private String artifactUri;
    private Boolean loaded;
    @JsonProperty("updated_at")
    private String updatedAt;

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

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getBackend() {
        return backend;
    }

    public void setBackend(String backend) {
        this.backend = backend;
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

    public String getArtifactUri() {
        return artifactUri;
    }

    public void setArtifactUri(String artifactUri) {
        this.artifactUri = artifactUri;
    }

    public Boolean getLoaded() {
        return loaded;
    }

    public void setLoaded(Boolean loaded) {
        this.loaded = loaded;
    }

    public String getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(String updatedAt) {
        this.updatedAt = updatedAt;
    }
}
