package com.bsl.autocomplete.api;

import com.bsl.autocomplete.api.dto.AutocompleteResponse;
import com.bsl.autocomplete.api.dto.ErrorResponse;
import com.bsl.autocomplete.opensearch.OpenSearchUnavailableException;
import com.bsl.autocomplete.service.AutocompleteService;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AutocompleteController {
    private static final int DEFAULT_SIZE = 10;
    private static final int MIN_SIZE = 1;
    private static final int MAX_SIZE = 20;

    private final AutocompleteService autocompleteService;

    public AutocompleteController(AutocompleteService autocompleteService) {
        this.autocompleteService = autocompleteService;
    }

    @GetMapping({"/autocomplete", "/v1/autocomplete"})
    public ResponseEntity<?> autocomplete(
        @RequestParam(value = "q", required = false) String query,
        @RequestParam(value = "size", required = false) Integer size,
        @RequestHeader(value = "x-trace-id", required = false) String traceHeader,
        @RequestHeader(value = "x-request-id", required = false) String requestHeader
    ) {
        long started = System.nanoTime();
        String traceId = RequestIdUtil.resolveOrGenerate(traceHeader);
        String requestId = RequestIdUtil.resolveOrGenerate(requestHeader);

        String trimmed = query == null ? "" : query.trim();
        int resolvedSize = clampSize(size);

        try {
            if (trimmed.isEmpty()) {
                return ResponseEntity.ok(emptyResponse(traceId, requestId, started));
            }
            return ResponseEntity.ok(autocompleteService.autocomplete(trimmed, resolvedSize, traceId, requestId));
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

    private int clampSize(Integer size) {
        int resolved = size == null ? DEFAULT_SIZE : size;
        if (resolved < MIN_SIZE) {
            return MIN_SIZE;
        }
        if (resolved > MAX_SIZE) {
            return MAX_SIZE;
        }
        return resolved;
    }

    private AutocompleteResponse emptyResponse(String traceId, String requestId, long started) {
        AutocompleteResponse response = new AutocompleteResponse();
        response.setVersion("v1");
        response.setTraceId(traceId);
        response.setRequestId(requestId);
        response.setTookMs((System.nanoTime() - started) / 1_000_000L);
        response.setSuggestions(List.of());
        return response;
    }
}
