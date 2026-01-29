package com.bsl.bff.api;

import com.bsl.bff.api.dto.BffSearchRequest;
import com.bsl.bff.api.dto.BffSearchResponse;
import com.bsl.bff.client.QueryServiceClient;
import com.bsl.bff.client.SearchServiceClient;
import com.bsl.bff.client.dto.DownstreamSearchRequest;
import com.bsl.bff.client.dto.SearchServiceResponse;
import com.bsl.bff.common.BadRequestException;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.outbox.OutboxService;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SearchController {
    private static final int DEFAULT_SIZE = 10;
    private static final int DEFAULT_FROM = 0;

    private final QueryServiceClient queryServiceClient;
    private final SearchServiceClient searchServiceClient;
    private final OutboxService outboxService;

    public SearchController(
        QueryServiceClient queryServiceClient,
        SearchServiceClient searchServiceClient,
        OutboxService outboxService
    ) {
        this.queryServiceClient = queryServiceClient;
        this.searchServiceClient = searchServiceClient;
        this.outboxService = outboxService;
    }

    @PostMapping("/search")
    public BffSearchResponse search(@RequestBody(required = false) BffSearchRequest request) {
        RequestContext context = RequestContextHolder.get();
        if (request == null) {
            throw new BadRequestException("request body is required");
        }

        String rawQuery = request.getQuery() != null ? request.getQuery().getRaw() : null;
        JsonNode queryContextV11 = request.getQueryContextV11();
        JsonNode queryContext = request.getQueryContext();

        if (queryContextV11 == null && queryContext == null) {
            if (rawQuery == null || rawQuery.trim().isEmpty()) {
                throw new BadRequestException("query.raw is required");
            }
            queryContextV11 = queryServiceClient.fetchQueryContext(rawQuery, context);
        }

        DownstreamSearchRequest downstreamRequest = new DownstreamSearchRequest();
        if (rawQuery != null && !rawQuery.trim().isEmpty()) {
            DownstreamSearchRequest.Query query = new DownstreamSearchRequest.Query();
            query.setRaw(rawQuery);
            downstreamRequest.setQuery(query);
        }
        downstreamRequest.setQueryContextV11(queryContextV11);
        downstreamRequest.setQueryContext(queryContext);
        downstreamRequest.setOptions(toDownstreamOptions(request));

        long started = System.nanoTime();
        SearchServiceResponse searchResponse = searchServiceClient.search(downstreamRequest, context);
        if (searchResponse == null) {
            throw new BadRequestException("search service response is empty");
        }

        BffSearchResponse response = new BffSearchResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setTookMs(searchResponse.getTookMs() > 0
            ? searchResponse.getTookMs()
            : (System.nanoTime() - started) / 1_000_000L);
        response.setTimedOut(false);

        List<SearchServiceResponse.BookHit> hits = searchResponse.getHits();
        List<BffSearchResponse.Hit> mapped = new ArrayList<>();
        if (hits != null) {
            for (SearchServiceResponse.BookHit hit : hits) {
                if (hit == null) {
                    continue;
                }
                BffSearchResponse.Hit mappedHit = new BffSearchResponse.Hit();
                mappedHit.setDocId(hit.getDocId());
                mappedHit.setScore(hit.getScore());
                if (hit.getSource() != null) {
                    mappedHit.setTitle(nullToEmpty(hit.getSource().getTitleKo()));
                    mappedHit.setAuthors(nullToEmptyList(hit.getSource().getAuthors()));
                    mappedHit.setPublisher(hit.getSource().getPublisherName());
                    mappedHit.setPublicationYear(hit.getSource().getIssuedYear());
                } else {
                    mappedHit.setTitle("");
                    mappedHit.setAuthors(List.of());
                }
                mapped.add(mappedHit);
            }
        }
        response.setHits(mapped);
        response.setTotal(mapped.size());

        Map<String, Object> payload = new HashMap<>();
        if (rawQuery != null) {
            payload.put("query", rawQuery);
        }
        payload.put("from", resolveFrom(request));
        payload.put("size", resolveSize(request));
        recordOutbox("search_request", "search", context, payload);

        return response;
    }

    private DownstreamSearchRequest.Options toDownstreamOptions(BffSearchRequest request) {
        DownstreamSearchRequest.Options options = new DownstreamSearchRequest.Options();
        int from = resolveFrom(request);
        int size = resolveSize(request);
        options.setFrom(from);
        options.setSize(size);
        if (request.getOptions() != null) {
            options.setEnableVector(request.getOptions().getEnableVector());
            options.setRrfK(request.getOptions().getRrfK());
        }
        return options;
    }

    private int resolveFrom(BffSearchRequest request) {
        if (request.getPagination() != null && request.getPagination().getFrom() != null) {
            return Math.max(request.getPagination().getFrom(), 0);
        }
        if (request.getOptions() != null && request.getOptions().getFrom() != null) {
            return Math.max(request.getOptions().getFrom(), 0);
        }
        return DEFAULT_FROM;
    }

    private int resolveSize(BffSearchRequest request) {
        if (request.getPagination() != null && request.getPagination().getSize() != null) {
            return Math.max(request.getPagination().getSize(), 1);
        }
        if (request.getOptions() != null && request.getOptions().getSize() != null) {
            return Math.max(request.getOptions().getSize(), 1);
        }
        return DEFAULT_SIZE;
    }

    private void recordOutbox(String eventType, String aggregateType, RequestContext context, Map<String, Object> payload) {
        if (context == null) {
            return;
        }
        Map<String, Object> enriched = new HashMap<>(payload);
        enriched.put("request_id", context.getRequestId());
        enriched.put("trace_id", context.getTraceId());
        outboxService.record(eventType, aggregateType, context.getRequestId(), enriched);
    }

    private String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    private List<String> nullToEmptyList(List<String> value) {
        return value == null ? List.of() : value;
    }
}
