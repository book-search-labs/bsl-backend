package com.bsl.search.api;

import com.bsl.search.api.dto.ErrorResponse;
import com.bsl.search.api.dto.SearchRequest;
import com.bsl.search.api.dto.SearchResponse;
import com.bsl.search.opensearch.OpenSearchUnavailableException;
import com.bsl.search.service.HybridSearchService;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SearchController {
    private final HybridSearchService searchService;

    public SearchController(HybridSearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @PostMapping("/search")
    public ResponseEntity<?> search(
        @RequestBody(required = false) SearchRequest request,
        @RequestHeader(value = "x-trace-id", required = false) String traceIdHeader,
        @RequestHeader(value = "x-request-id", required = false) String requestIdHeader
    ) {
        String traceId = normalizeOrGenerate(traceIdHeader);
        String requestId = normalizeOrGenerate(requestIdHeader);

        if (request == null || request.getQuery() == null || isBlank(request.getQuery().getRaw())) {
            return ResponseEntity.badRequest().body(
                new ErrorResponse("bad_request", "query.raw is required", traceId, requestId)
            );
        }

        try {
            SearchResponse response = searchService.search(request, traceId, requestId);
            return ResponseEntity.ok(response);
        } catch (OpenSearchUnavailableException e) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(
                new ErrorResponse("opensearch_unavailable", "OpenSearch is unavailable", traceId, requestId)
            );
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(
                new ErrorResponse("internal_error", "Unexpected error", traceId, requestId)
            );
        }
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private String normalizeOrGenerate(String value) {
        if (value != null && !value.trim().isEmpty()) {
            return value;
        }
        return UUID.randomUUID().toString();
    }
}
