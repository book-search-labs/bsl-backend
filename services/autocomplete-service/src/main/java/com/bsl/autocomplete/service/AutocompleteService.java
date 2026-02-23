package com.bsl.autocomplete.service;

import com.bsl.autocomplete.api.dto.AutocompleteResponse;
import com.bsl.autocomplete.cache.AutocompleteCacheService;
import com.bsl.autocomplete.opensearch.OpenSearchGateway;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class AutocompleteService {
    private static final String SOURCE_OS = "opensearch";
    private static final int FETCH_MULTIPLIER = 3;
    private static final int FETCH_MAX = 50;
    private static final String VERSION = "v1";

    private final OpenSearchGateway openSearchGateway;
    private final AutocompleteCacheService cacheService;

    public AutocompleteService(OpenSearchGateway openSearchGateway, AutocompleteCacheService cacheService) {
        this.openSearchGateway = openSearchGateway;
        this.cacheService = cacheService;
    }

    public AutocompleteResponse autocomplete(String query, int size, String traceId, String requestId) {
        long started = System.nanoTime();

        List<AutocompleteResponse.Suggestion> suggestions = query == null || query.isBlank()
            ? buildTrendingSuggestions(size)
            : buildSuggestions(query, size);

        AutocompleteResponse response = new AutocompleteResponse();
        response.setVersion(VERSION);
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

        Optional<List<AutocompleteResponse.Suggestion>> cached = cacheService.get(query, size);
        if (cached.isPresent()) {
            return cached.get();
        }

        int fetchSize = Math.min(size * FETCH_MULTIPLIER, FETCH_MAX);
        List<OpenSearchGateway.SuggestionHit> hits = openSearchGateway.searchSuggestions(query, fetchSize);

        Map<String, OpenSearchGateway.SuggestionHit> deduped = new LinkedHashMap<>();
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
                deduped.put(key, hit);
                scores.put(key, hit.getScore());
            } else {
                Double existingScore = scores.get(key);
                if (existingScore == null || hit.getScore() > existingScore) {
                    scores.put(key, hit.getScore());
                    deduped.put(key, hit);
                }
            }
            if (deduped.size() >= size) {
                break;
            }
        }

        List<AutocompleteResponse.Suggestion> suggestions = new ArrayList<>();
        for (Map.Entry<String, OpenSearchGateway.SuggestionHit> entry : deduped.entrySet()) {
            OpenSearchGateway.SuggestionHit hit = entry.getValue();
            AutocompleteResponse.Suggestion suggestion = new AutocompleteResponse.Suggestion();
            suggestion.setText(hit.getText());
            suggestion.setScore(scores.getOrDefault(entry.getKey(), 0.0));
            suggestion.setSource(SOURCE_OS);
            suggestion.setSuggestId(hit.getSuggestId());
            suggestion.setType(hit.getType());
            suggestion.setTargetDocId(hit.getTargetDocId());
            suggestion.setTargetId(hit.getTargetId());
            suggestions.add(suggestion);
        }
        cacheService.put(query, suggestions);
        return suggestions;
    }

    private List<AutocompleteResponse.Suggestion> buildTrendingSuggestions(int size) {
        if (size <= 0) {
            return List.of();
        }

        List<OpenSearchGateway.SuggestionHit> hits = openSearchGateway.searchTrendingSuggestions(size);
        if (hits == null || hits.isEmpty()) {
            return List.of();
        }

        List<AutocompleteResponse.Suggestion> suggestions = new ArrayList<>();
        Map<String, Boolean> dedup = new LinkedHashMap<>();
        for (OpenSearchGateway.SuggestionHit hit : hits) {
            String text = hit.getText();
            if (text == null || text.isBlank()) {
                continue;
            }
            String key = text.trim().toLowerCase(Locale.ROOT);
            if (dedup.containsKey(key)) {
                continue;
            }
            dedup.put(key, true);

            AutocompleteResponse.Suggestion suggestion = new AutocompleteResponse.Suggestion();
            suggestion.setText(text);
            suggestion.setScore(hit.getScore());
            suggestion.setSource(SOURCE_OS);
            suggestion.setSuggestId(hit.getSuggestId());
            suggestion.setType(hit.getType());
            suggestion.setTargetDocId(hit.getTargetDocId());
            suggestion.setTargetId(hit.getTargetId());
            suggestions.add(suggestion);

            if (suggestions.size() >= size) {
                break;
            }
        }
        return suggestions;
    }
}
