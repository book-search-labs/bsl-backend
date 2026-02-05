package com.bsl.search.api;

import com.bsl.search.api.dto.ErrorResponse;
import com.bsl.search.api.dto.QueryContext;
import com.bsl.search.api.dto.QueryContextV1_1;
import com.bsl.search.api.dto.SearchRequest;
import com.bsl.search.api.dto.SearchResponse;
import com.bsl.search.opensearch.OpenSearchUnavailableException;
import com.bsl.search.service.BookDetailResult;
import com.bsl.search.service.HybridSearchService;
import com.bsl.search.service.InvalidSearchRequestException;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
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

    @PostMapping({"/search", "/internal/search"})
    public ResponseEntity<?> search(
        @RequestBody(required = false) SearchRequest request,
        @RequestHeader(value = "x-trace-id", required = false) String traceIdHeader,
        @RequestHeader(value = "x-request-id", required = false) String requestIdHeader,
        @RequestHeader(value = "traceparent", required = false) String traceparent
    ) {
        RequestKind kind = resolveKind(request);
        String traceId = resolveTraceId(kind, request, traceIdHeader, traceparent);
        String requestId = resolveRequestId(kind, request, requestIdHeader);

        if (request == null) {
            return ResponseEntity.badRequest().body(
                new ErrorResponse("bad_request", "request body is required", traceId, requestId)
            );
        }

        try {
            SearchResponse response = searchService.search(request, traceId, requestId, traceparent);
            return ResponseEntity.ok(response);
        } catch (InvalidSearchRequestException e) {
            return ResponseEntity.badRequest().body(
                new ErrorResponse("bad_request", e.getMessage(), traceId, requestId)
            );
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

    @PostMapping("/internal/explain")
    public ResponseEntity<?> explain(
        @RequestBody(required = false) SearchRequest request,
        @RequestHeader(value = "x-trace-id", required = false) String traceIdHeader,
        @RequestHeader(value = "x-request-id", required = false) String requestIdHeader,
        @RequestHeader(value = "traceparent", required = false) String traceparent
    ) {
        return search(withExplainOptions(request), traceIdHeader, requestIdHeader, traceparent);
    }

    @GetMapping("/books/{docId}")
    public ResponseEntity<?> getBookById(
        @PathVariable("docId") String docId,
        @RequestHeader(value = "x-trace-id", required = false) String traceIdHeader,
        @RequestHeader(value = "x-request-id", required = false) String requestIdHeader,
        @RequestHeader(value = "If-None-Match", required = false) String ifNoneMatch
    ) {
        String traceId = normalizeOrGenerate(traceIdHeader);
        String requestId = normalizeOrGenerate(requestIdHeader);

        if (docId == null || docId.trim().isEmpty()) {
            return ResponseEntity.badRequest().body(
                new ErrorResponse("bad_request", "docId is required", traceId, requestId)
            );
        }

        try {
            BookDetailResult result = searchService.getBookById(docId, traceId, requestId);
            if (result == null || result.getResponse() == null) {
                return ResponseEntity.status(HttpStatus.NOT_FOUND).body(
                    new ErrorResponse("not_found", "Book not found", traceId, requestId)
                );
            }
            String etag = result.getEtag();
            CacheControl cacheControl = CacheControl.maxAge(result.getCacheControlMaxAgeSeconds(), TimeUnit.SECONDS)
                .cachePublic();

            if (etag != null && ifNoneMatch != null && ifNoneMatch.equals(etag)) {
                return ResponseEntity.status(HttpStatus.NOT_MODIFIED)
                    .eTag(etag)
                    .cacheControl(cacheControl)
                    .build();
            }
            return ResponseEntity.ok()
                .eTag(etag)
                .cacheControl(cacheControl)
                .body(result.getResponse());
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

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleInvalidJson(HttpMessageNotReadableException e, HttpServletRequest request) {
        String traceId = normalizeOrGenerate(request.getHeader("x-trace-id"));
        String requestId = normalizeOrGenerate(request.getHeader("x-request-id"));
        return ResponseEntity.badRequest().body(
            new ErrorResponse("bad_request", "invalid JSON", traceId, requestId)
        );
    }

    private RequestKind resolveKind(SearchRequest request) {
        if (request == null) {
            return RequestKind.LEGACY;
        }
        if (request.getQueryContextV1_1() != null) {
            return RequestKind.QC_V1_1;
        }
        if (request.getQueryContext() != null) {
            return RequestKind.QC_V1;
        }
        return RequestKind.LEGACY;
    }

    private String resolveTraceId(RequestKind kind, SearchRequest request, String headerValue, String traceparent) {
        if (kind == RequestKind.QC_V1_1) {
            QueryContextV1_1 context = request.getQueryContextV1_1();
            String fromContext = context != null && context.getMeta() != null
                ? context.getMeta().getTraceId()
                : null;
            return normalizeOrGenerate(fromContext);
        }
        if (kind == RequestKind.QC_V1) {
            QueryContext context = request.getQueryContext();
            String fromContext = context == null ? null : context.getTraceId();
            return normalizeOrGenerate(fromContext);
        }
        String normalized = normalize(headerValue);
        if (normalized != null) {
            return normalized;
        }
        String fromTraceparent = extractTraceId(traceparent);
        if (fromTraceparent != null) {
            return fromTraceparent;
        }
        return UUID.randomUUID().toString();
    }

    private String resolveRequestId(RequestKind kind, SearchRequest request, String headerValue) {
        if (kind == RequestKind.QC_V1_1) {
            QueryContextV1_1 context = request.getQueryContextV1_1();
            String fromContext = context != null && context.getMeta() != null
                ? context.getMeta().getRequestId()
                : null;
            return normalizeOrGenerate(fromContext);
        }
        if (kind == RequestKind.QC_V1) {
            QueryContext context = request.getQueryContext();
            String fromContext = context == null ? null : context.getRequestId();
            return normalizeOrGenerate(fromContext);
        }
        return normalizeOrGenerate(headerValue);
    }

    private String normalizeOrGenerate(String value) {
        if (value != null && !value.trim().isEmpty()) {
            return value;
        }
        return UUID.randomUUID().toString();
    }

    private String normalize(String value) {
        if (value != null && !value.trim().isEmpty()) {
            return value;
        }
        return null;
    }

    private String extractTraceId(String traceparent) {
        if (traceparent == null || traceparent.isBlank()) {
            return null;
        }
        String[] parts = traceparent.trim().split("-");
        if (parts.length != 4) {
            return null;
        }
        return parts[1];
    }

    private SearchRequest withExplainOptions(SearchRequest request) {
        if (request == null) {
            return null;
        }
        com.bsl.search.api.dto.Options options = request.getOptions();
        if (options == null) {
            options = new com.bsl.search.api.dto.Options();
            request.setOptions(options);
        }
        options.setDebug(true);
        options.setExplain(true);
        return request;
    }

    private enum RequestKind {
        QC_V1_1,
        QC_V1,
        LEGACY
    }
}
