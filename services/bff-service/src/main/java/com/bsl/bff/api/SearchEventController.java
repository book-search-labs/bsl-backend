package com.bsl.bff.api;

import com.bsl.bff.api.dto.BffAckResponse;
import com.bsl.bff.api.dto.BffSearchClickRequest;
import com.bsl.bff.api.dto.BffSearchDwellRequest;
import com.bsl.bff.common.BadRequestException;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.outbox.OutboxService;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SearchEventController {
    private final OutboxService outboxService;

    public SearchEventController(OutboxService outboxService) {
        this.outboxService = outboxService;
    }

    @PostMapping("/search/click")
    public BffAckResponse recordClick(@RequestBody(required = false) BffSearchClickRequest request) {
        RequestContext context = RequestContextHolder.get();
        if (request == null) {
            throw new BadRequestException("request body is required");
        }
        String impId = safeTrim(request.getImpId());
        String docId = safeTrim(request.getDocId());
        String queryHash = safeTrim(request.getQueryHash());
        Integer position = request.getPosition();
        if (impId.isEmpty()) {
            throw new BadRequestException("imp_id is required");
        }
        if (docId.isEmpty()) {
            throw new BadRequestException("doc_id is required");
        }
        if (queryHash.isEmpty()) {
            throw new BadRequestException("query_hash is required");
        }
        if (position == null || position < 1) {
            throw new BadRequestException("position is required");
        }

        Map<String, Object> payload = new HashMap<>();
        payload.put("imp_id", impId);
        payload.put("doc_id", docId);
        payload.put("position", position);
        payload.put("query_hash", queryHash);
        payload.put("experiment_id", safeTrimOrNull(request.getExperimentId()));
        payload.put("policy_id", safeTrimOrNull(request.getPolicyId()));
        payload.put("event_time", OffsetDateTime.now(ZoneOffset.UTC).toString());
        enrichAndRecord("search_click", context, payload, buildAggregateId(impId, docId, position));

        return ack(context);
    }

    @PostMapping("/search/dwell")
    public BffAckResponse recordDwell(@RequestBody(required = false) BffSearchDwellRequest request) {
        RequestContext context = RequestContextHolder.get();
        if (request == null) {
            throw new BadRequestException("request body is required");
        }
        String impId = safeTrim(request.getImpId());
        String docId = safeTrim(request.getDocId());
        String queryHash = safeTrim(request.getQueryHash());
        Integer position = request.getPosition();
        Long dwellMs = request.getDwellMs();
        if (impId.isEmpty()) {
            throw new BadRequestException("imp_id is required");
        }
        if (docId.isEmpty()) {
            throw new BadRequestException("doc_id is required");
        }
        if (queryHash.isEmpty()) {
            throw new BadRequestException("query_hash is required");
        }
        if (position == null || position < 1) {
            throw new BadRequestException("position is required");
        }
        if (dwellMs == null || dwellMs < 0) {
            throw new BadRequestException("dwell_ms is required");
        }

        Map<String, Object> payload = new HashMap<>();
        payload.put("imp_id", impId);
        payload.put("doc_id", docId);
        payload.put("position", position);
        payload.put("query_hash", queryHash);
        payload.put("experiment_id", safeTrimOrNull(request.getExperimentId()));
        payload.put("policy_id", safeTrimOrNull(request.getPolicyId()));
        payload.put("dwell_ms", dwellMs);
        payload.put("event_time", OffsetDateTime.now(ZoneOffset.UTC).toString());
        enrichAndRecord("search_dwell", context, payload, buildAggregateId(impId, docId, position));

        return ack(context);
    }

    private void enrichAndRecord(
        String eventType,
        RequestContext context,
        Map<String, Object> payload,
        String aggregateId
    ) {
        if (context == null) {
            return;
        }
        payload.put("request_id", context.getRequestId());
        payload.put("trace_id", context.getTraceId());
        outboxService.record(eventType, "search", aggregateId, payload);
    }

    private BffAckResponse ack(RequestContext context) {
        BffAckResponse response = new BffAckResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setStatus("ok");
        return response;
    }

    private String buildAggregateId(String impId, String docId, Integer position) {
        return impId + ":" + docId + ":" + position;
    }

    private String safeTrim(String value) {
        return value == null ? "" : value.trim();
    }

    private String safeTrimOrNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
