package com.bsl.bff.ops.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class JobRunDto {
    @JsonProperty("job_run_id")
    private Long jobRunId;

    @JsonProperty("job_type")
    private String jobType;

    private String status;

    @JsonProperty("params")
    private Object params;

    @JsonProperty("error_message")
    private String errorMessage;

    @JsonProperty("started_at")
    private Instant startedAt;

    @JsonProperty("finished_at")
    private Instant finishedAt;

    public Long getJobRunId() {
        return jobRunId;
    }

    public void setJobRunId(Long jobRunId) {
        this.jobRunId = jobRunId;
    }

    public String getJobType() {
        return jobType;
    }

    public void setJobType(String jobType) {
        this.jobType = jobType;
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
}
