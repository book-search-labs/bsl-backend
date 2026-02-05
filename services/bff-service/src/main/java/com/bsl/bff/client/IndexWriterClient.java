package com.bsl.bff.client;

import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.common.DownstreamHeaders;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.config.DownstreamProperties;
import com.bsl.bff.ops.dto.ReindexJobCreateRequest;
import com.bsl.bff.ops.dto.ReindexJobDto;
import com.bsl.bff.ops.dto.ReindexJobResponse;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

@Component
public class IndexWriterClient {
    private final RestTemplate restTemplate;
    private final DownstreamProperties.ServiceProperties properties;

    public IndexWriterClient(RestTemplate indexWriterRestTemplate, DownstreamProperties downstreamProperties) {
        this.restTemplate = indexWriterRestTemplate;
        this.properties = downstreamProperties.getIndexWriterService();
    }

    public ReindexJobDto createReindexJob(ReindexJobCreateRequest request, RequestContext context) {
        String url = properties.getBaseUrl() + "/internal/index/reindex-jobs";
        HttpHeaders headers = DownstreamHeaders.from(context);
        headers.add(HttpHeaders.CONTENT_TYPE, "application/json");
        HttpEntity<ReindexJobCreateRequest> entity = new HttpEntity<>(request, headers);
        return execute(url, HttpMethod.POST, entity);
    }

    public ReindexJobDto pauseReindexJob(long jobId, RequestContext context) {
        return executeAction(jobId, "pause", context);
    }

    public ReindexJobDto resumeReindexJob(long jobId, RequestContext context) {
        return executeAction(jobId, "resume", context);
    }

    public ReindexJobDto retryReindexJob(long jobId, RequestContext context) {
        return executeAction(jobId, "retry", context);
    }

    private ReindexJobDto executeAction(long jobId, String action, RequestContext context) {
        String url = properties.getBaseUrl() + "/internal/index/reindex-jobs/" + jobId + "/" + action;
        HttpHeaders headers = DownstreamHeaders.from(context);
        headers.add(HttpHeaders.CONTENT_TYPE, "application/json");
        HttpEntity<Void> entity = new HttpEntity<>(headers);
        return execute(url, HttpMethod.POST, entity);
    }

    private ReindexJobDto execute(String url, HttpMethod method, HttpEntity<?> entity) {
        try {
            ResponseEntity<ReindexJobResponse> response = restTemplate.exchange(url, method, entity, ReindexJobResponse.class);
            ReindexJobResponse body = response.getBody();
            if (body == null || body.getJob() == null) {
                throw new DownstreamException(HttpStatus.BAD_GATEWAY, "index_writer_empty", "Index writer response empty");
            }
            return body.getJob();
        } catch (ResourceAccessException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "index_writer_timeout", "Index writer timeout");
        } catch (HttpStatusCodeException ex) {
            HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
            if (status == null) {
                status = HttpStatus.SERVICE_UNAVAILABLE;
            }
            throw new DownstreamException(status, "index_writer_error", "Index writer error");
        }
    }
}
