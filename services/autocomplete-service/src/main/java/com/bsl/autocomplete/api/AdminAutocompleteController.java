package com.bsl.autocomplete.api;

import com.bsl.autocomplete.api.dto.AdminAutocompleteResponse;
import com.bsl.autocomplete.api.dto.AdminAutocompleteUpdateRequest;
import com.bsl.autocomplete.api.dto.AdminAutocompleteUpdateResponse;
import com.bsl.autocomplete.api.dto.ErrorResponse;
import com.bsl.autocomplete.opensearch.OpenSearchGateway;
import com.bsl.autocomplete.opensearch.OpenSearchUnavailableException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/autocomplete")
public class AdminAutocompleteController {
    private static final int DEFAULT_SIZE = 20;
    private static final int MIN_SIZE = 1;
    private static final int MAX_SIZE = 50;

    private final OpenSearchGateway openSearchGateway;

    public AdminAutocompleteController(OpenSearchGateway openSearchGateway) {
        this.openSearchGateway = openSearchGateway;
    }

    @GetMapping("/suggestions")
    public ResponseEntity<?> searchSuggestions(
        @RequestParam(value = "q", required = false) String query,
        @RequestParam(value = "size", required = false) Integer size,
        @RequestParam(value = "include_blocked", required = false) Boolean includeBlocked,
        @RequestHeader(value = "x-trace-id", required = false) String traceHeader,
        @RequestHeader(value = "x-request-id", required = false) String requestHeader
    ) {
        long started = System.nanoTime();
        String traceId = RequestIdUtil.resolveOrGenerate(traceHeader);
        String requestId = RequestIdUtil.resolveOrGenerate(requestHeader);
        String trimmed = query == null ? "" : query.trim();
        int resolvedSize = clampSize(size);

        try {
            AdminAutocompleteResponse response = new AdminAutocompleteResponse();
            response.setTookMs((System.nanoTime() - started) / 1_000_000L);
            if (trimmed.isEmpty()) {
                response.setSuggestions(List.of());
                return ResponseEntity.ok(response);
            }
            List<OpenSearchGateway.SuggestionHit> hits =
                openSearchGateway.searchAdminSuggestions(trimmed, resolvedSize, includeBlocked != null && includeBlocked);
            List<AdminAutocompleteResponse.Suggestion> mapped = new ArrayList<>();
            for (OpenSearchGateway.SuggestionHit hit : hits) {
                AdminAutocompleteResponse.Suggestion suggestion = toAdminSuggestion(hit);
                mapped.add(suggestion);
            }
            response.setSuggestions(mapped);
            response.setTookMs((System.nanoTime() - started) / 1_000_000L);
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

    @PostMapping("/suggestions/{suggestId}")
    public ResponseEntity<?> updateSuggestion(
        @PathVariable("suggestId") String suggestId,
        @RequestBody(required = false) AdminAutocompleteUpdateRequest request,
        @RequestHeader(value = "x-trace-id", required = false) String traceHeader,
        @RequestHeader(value = "x-request-id", required = false) String requestHeader
    ) {
        String traceId = RequestIdUtil.resolveOrGenerate(traceHeader);
        String requestId = RequestIdUtil.resolveOrGenerate(requestHeader);
        if (suggestId == null || suggestId.isBlank()) {
            return ResponseEntity.badRequest().body(
                new ErrorResponse("bad_request", "suggest_id is required", traceId, requestId)
            );
        }
        if (request == null || (request.getWeight() == null && request.getBlocked() == null)) {
            return ResponseEntity.badRequest().body(
                new ErrorResponse("bad_request", "weight or is_blocked is required", traceId, requestId)
            );
        }
        if (request.getWeight() != null && request.getWeight() < 0) {
            return ResponseEntity.badRequest().body(
                new ErrorResponse("bad_request", "weight must be >= 0", traceId, requestId)
            );
        }

        try {
            Map<String, Object> fields = new LinkedHashMap<>();
            if (request.getWeight() != null) {
                fields.put("weight", request.getWeight());
            }
            if (request.getBlocked() != null) {
                fields.put("is_blocked", request.getBlocked());
            }
            fields.put("updated_at", Instant.now().toString());
            OpenSearchGateway.SuggestionHit existing = openSearchGateway.getSuggestion(suggestId);
            if (existing == null) {
                return ResponseEntity.status(HttpStatus.NOT_FOUND).body(
                    new ErrorResponse("not_found", "suggestion not found", traceId, requestId)
                );
            }
            openSearchGateway.updateSuggestion(suggestId, fields);
            OpenSearchGateway.SuggestionHit updated = openSearchGateway.getSuggestion(suggestId);
            AdminAutocompleteUpdateResponse response = new AdminAutocompleteUpdateResponse();
            response.setSuggestion(toAdminSuggestion(updated == null ? existing : updated));
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

    private AdminAutocompleteResponse.Suggestion toAdminSuggestion(OpenSearchGateway.SuggestionHit hit) {
        AdminAutocompleteResponse.Suggestion suggestion = new AdminAutocompleteResponse.Suggestion();
        suggestion.setSuggestId(hit.getSuggestId());
        suggestion.setText(hit.getText());
        suggestion.setType(hit.getType());
        suggestion.setLang(hit.getLang());
        suggestion.setTargetId(hit.getTargetId());
        suggestion.setTargetDocId(hit.getTargetDocId());
        suggestion.setWeight(hit.getWeight());
        suggestion.setCtr7d(hit.getCtr7d());
        suggestion.setPopularity7d(hit.getPopularity7d());
        suggestion.setBlocked(hit.isBlocked());
        return suggestion;
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
}
