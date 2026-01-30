package com.bsl.bff.ops.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class ReindexJobDto {
    @JsonProperty("reindex_job_id")
    private Long reindexJobId;

    @JsonProperty("logical_name")
    private String logicalName;

    @JsonProperty("from_physical")
    private String fromPhysical;

    @JsonProperty("to_physical")
    private String toPhysical;

    private String status;

    private Object params;
    private Object progress;
    private Object error;

    @JsonProperty("error_message")
    private String errorMessage;

    @JsonProperty("started_at")
    private Instant startedAt;

    @JsonProperty("finished_at")
    private Instant finishedAt;

    @JsonProperty("created_at")
    private Instant createdAt;

    @JsonProperty("updated_at")
    private Instant updatedAt;

    @JsonProperty("paused_at")
    private Instant pausedAt;

    public Long getReindexJobId() {
        return reindexJobId;
    }

    public void setReindexJobId(Long reindexJobId) {
        this.reindexJobId = reindexJobId;
    }

    public String getLogicalName() {
        return logicalName;
    }

    public void setLogicalName(String logicalName) {
        this.logicalName = logicalName;
    }

    public String getFromPhysical() {
        return fromPhysical;
    }

    public void setFromPhysical(String fromPhysical) {
        this.fromPhysical = fromPhysical;
    }

    public String getToPhysical() {
        return toPhysical;
    }

    public void setToPhysical(String toPhysical) {
        this.toPhysical = toPhysical;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Object getParams() {
        return params;
    }

    public void setParams(Object params) {
        this.params = params;
    }

    public Object getProgress() {
        return progress;
    }

    public void setProgress(Object progress) {
        this.progress = progress;
    }

    public Object getError() {
        return error;
    }

    public void setError(Object error) {
        this.error = error;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }

    public Instant getStartedAt() {
        return startedAt;
    }

    public void setStartedAt(Instant startedAt) {
        this.startedAt = startedAt;
    }

    public Instant getFinishedAt() {
        return finishedAt;
    }

    public void setFinishedAt(Instant finishedAt) {
        this.finishedAt = finishedAt;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(Instant updatedAt) {
        this.updatedAt = updatedAt;
    }

    public Instant getPausedAt() {
        return pausedAt;
    }

    public void setPausedAt(Instant pausedAt) {
        this.pausedAt = pausedAt;
    }
}
