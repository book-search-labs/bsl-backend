package com.bsl.autocomplete.service;

import com.bsl.autocomplete.api.dto.AutocompleteResponse;
import com.bsl.autocomplete.opensearch.OpenSearchGateway;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class AutocompleteService {
    private static final String SOURCE = "opensearch";
    private static final int FETCH_MULTIPLIER = 3;
    private static final int FETCH_MAX = 50;

    private final OpenSearchGateway openSearchGateway;

    public AutocompleteService(OpenSearchGateway openSearchGateway) {
        this.openSearchGateway = openSearchGateway;
    }

    public AutocompleteResponse autocomplete(String query, int size, String traceId, String requestId) {
        long started = System.nanoTime();

        List<AutocompleteResponse.Suggestion> suggestions = buildSuggestions(query, size);

        AutocompleteResponse response = new AutocompleteResponse();
        response.setTraceId(traceId);
        response.setRequestId(requestId);
        response.setTookMs((System.nanoTime() - started) / 1_000_000L);
        response.setSuggestions(suggestions);
        return response;
    }

    private List<AutocompleteResponse.Suggestion> buildSuggestions(String query, int size) {
        if (query == null || query.isBlank() || size <= 0) {
            return List.of();
        }

        int fetchSize = Math.min(size * FETCH_MULTIPLIER, FETCH_MAX);
        List<OpenSearchGateway.SuggestionHit> hits = openSearchGateway.searchSuggestions(query, fetchSize);

        Map<String, String> deduped = new LinkedHashMap<>();
        Map<String, Double> scores = new LinkedHashMap<>();
        for (OpenSearchGateway.SuggestionHit hit : hits) {
            String candidate = hit.getText();
            if (candidate == null) {
                continue;
            }
            String trimmed = candidate.trim();
            if (trimmed.isEmpty()) {
                continue;
            }
            String key = trimmed.toLowerCase(Locale.ROOT);
            if (!deduped.containsKey(key)) {
                deduped.put(key, trimmed);
                scores.put(key, hit.getScore());
            } else {
                Double existingScore = scores.get(key);
                if (existingScore == null || hit.getScore() > existingScore) {
                    scores.put(key, hit.getScore());
                }
            }
            if (deduped.size() >= size) {
                break;
            }
        }

        List<AutocompleteResponse.Suggestion> suggestions = new ArrayList<>();
        for (Map.Entry<String, String> entry : deduped.entrySet()) {
            AutocompleteResponse.Suggestion suggestion = new AutocompleteResponse.Suggestion();
            suggestion.setText(entry.getValue());
            suggestion.setScore(scores.getOrDefault(entry.getKey(), 0.0));
            suggestion.setSource(SOURCE);
            suggestions.add(suggestion);
        }
        return suggestions;
    }
}
