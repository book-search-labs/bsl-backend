package com.bsl.bff.ops;

import com.bsl.bff.client.IndexWriterClient;
import com.bsl.bff.common.BadRequestException;
import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.ops.dto.JobRunDto;
import com.bsl.bff.ops.dto.JobRunResponse;
import com.bsl.bff.ops.dto.OpsListResponse;
import com.bsl.bff.ops.dto.OpsTaskDto;
import com.bsl.bff.ops.dto.ReindexJobCreateRequest;
import com.bsl.bff.ops.dto.ReindexJobDto;
import com.bsl.bff.ops.dto.ReindexJobResponse;
import java.util.List;
import java.util.Optional;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/admin/ops")
public class OpsController {
    private static final int DEFAULT_LIMIT = 50;
    private static final int MAX_LIMIT = 500;

    private final OpsRepository repository;
    private final IndexWriterClient indexWriterClient;

    public OpsController(OpsRepository repository, IndexWriterClient indexWriterClient) {
        this.repository = repository;
        this.indexWriterClient = indexWriterClient;
    }

    @GetMapping("/job-runs")
    public OpsListResponse<JobRunDto> listJobRuns(
        @RequestParam(value = "limit", required = false) Integer limit,
        @RequestParam(value = "status", required = false) String status
    ) {
        int resolvedLimit = clampLimit(limit);
        List<JobRunDto> items = repository.fetchJobRuns(resolvedLimit, status);
        return buildListResponse(items);
    }

    @GetMapping("/job-runs/{id}")
    public JobRunResponse getJobRun(@PathVariable("id") long jobRunId) {
        Optional<JobRunDto> existing = repository.findJobRun(jobRunId);
        if (existing.isEmpty()) {
            throw new DownstreamException(HttpStatus.NOT_FOUND, "not_found", "job_run not found");
        }
        return buildJobRunResponse(existing.get());
    }

    @PostMapping("/job-runs/{id}/retry")
    public JobRunResponse retryJobRun(@PathVariable("id") long jobRunId) {
        Optional<JobRunDto> existing = repository.findJobRun(jobRunId);
        if (existing.isEmpty()) {
            throw new DownstreamException(HttpStatus.NOT_FOUND, "not_found", "job_run not found");
        }
        JobRunDto retried = repository.insertJobRunRetry(existing.get());
        return buildJobRunResponse(retried);
    }

    @GetMapping("/reindex-jobs")
    public OpsListResponse<ReindexJobDto> listReindexJobs(
        @RequestParam(value = "limit", required = false) Integer limit,
        @RequestParam(value = "status", required = false) String status,
        @RequestParam(value = "logical_name", required = false) String logicalName
    ) {
        int resolvedLimit = clampLimit(limit);
        List<ReindexJobDto> items = repository.fetchReindexJobs(resolvedLimit, status, logicalName);
        return buildListResponse(items);
    }

    @PostMapping("/reindex-jobs/start")
    public ReindexJobResponse startReindex(@RequestBody(required = false) ReindexJobCreateRequest request) {
        if (request == null || request.getLogicalName() == null || request.getLogicalName().isBlank()) {
            throw new BadRequestException("logical_name is required");
        }
        RequestContext context = RequestContextHolder.get();
        ReindexJobDto job = indexWriterClient.createReindexJob(request, context);
        return buildReindexJobResponse(job);
    }

    @PostMapping("/reindex-jobs/{id}/pause")
    public ReindexJobResponse pauseReindex(@PathVariable("id") long jobId) {
        RequestContext context = RequestContextHolder.get();
        ReindexJobDto job = indexWriterClient.pauseReindexJob(jobId, context);
        return buildReindexJobResponse(job);
    }

    @PostMapping("/reindex-jobs/{id}/resume")
    public ReindexJobResponse resumeReindex(@PathVariable("id") long jobId) {
        RequestContext context = RequestContextHolder.get();
        ReindexJobDto job = indexWriterClient.resumeReindexJob(jobId, context);
        return buildReindexJobResponse(job);
    }

    @PostMapping("/reindex-jobs/{id}/retry")
    public ReindexJobResponse retryReindex(@PathVariable("id") long jobId) {
        RequestContext context = RequestContextHolder.get();
        ReindexJobDto job = indexWriterClient.retryReindexJob(jobId, context);
        return buildReindexJobResponse(job);
    }

    @GetMapping("/tasks")
    public OpsListResponse<OpsTaskDto> listOpsTasks(
        @RequestParam(value = "limit", required = false) Integer limit,
        @RequestParam(value = "status", required = false) String status,
        @RequestParam(value = "task_type", required = false) String taskType
    ) {
        int resolvedLimit = clampLimit(limit);
        List<OpsTaskDto> items = repository.fetchOpsTasks(resolvedLimit, status, taskType);
        return buildListResponse(items);
    }

    private int clampLimit(Integer limit) {
        int value = limit == null ? DEFAULT_LIMIT : limit;
        if (value < 1) {
            value = DEFAULT_LIMIT;
        }
        return Math.min(value, MAX_LIMIT);
    }

    private <T> OpsListResponse<T> buildListResponse(List<T> items) {
        RequestContext context = RequestContextHolder.get();
        OpsListResponse<T> response = new OpsListResponse<>();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setItems(items);
        response.setCount(items == null ? 0 : items.size());
        return response;
    }

    private JobRunResponse buildJobRunResponse(JobRunDto jobRun) {
        RequestContext context = RequestContextHolder.get();
        JobRunResponse response = new JobRunResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setJobRun(jobRun);
        return response;
    }

    private ReindexJobResponse buildReindexJobResponse(ReindexJobDto job) {
        RequestContext context = RequestContextHolder.get();
        ReindexJobResponse response = new ReindexJobResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setJob(job);
        return response;
    }
}
