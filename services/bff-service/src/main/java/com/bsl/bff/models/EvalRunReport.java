package com.bsl.bff.models;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;

@JsonIgnoreProperties(ignoreUnknown = true)
public class EvalRunReport {
    @JsonProperty("run_id")
    private String runId;
    @JsonProperty("generated_at")
    private String generatedAt;
    private Map<String, Map<String, Object>> sets;
    private Map<String, Object> overall;
    @JsonProperty("baseline_id")
    private String baselineId;

    public String getRunId() {
        return runId;
    }

    public void setRunId(String runId) {
        this.runId = runId;
    }

    public String getGeneratedAt() {
        return generatedAt;
    }

    public void setGeneratedAt(String generatedAt) {
        this.generatedAt = generatedAt;
    }

    public Map<String, Map<String, Object>> getSets() {
        return sets;
    }

    public void setSets(Map<String, Map<String, Object>> sets) {
        this.sets = sets;
    }

    public Map<String, Object> getOverall() {
        return overall;
    }

    public void setOverall(Map<String, Object> overall) {
        this.overall = overall;
    }

    public String getBaselineId() {
        return baselineId;
    }

    public void setBaselineId(String baselineId) {
        this.baselineId = baselineId;
    }
}
