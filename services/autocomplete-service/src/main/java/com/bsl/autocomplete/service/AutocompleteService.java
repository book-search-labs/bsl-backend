package com.bsl.autocomplete.service;

import com.bsl.autocomplete.api.dto.AutocompleteResponse;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class AutocompleteService {
    private static final String SOURCE = "mvp";
    private static final double SCORE_STEP = 0.1;
    private static final double SCORE_FLOOR = 0.1;

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

        List<String> candidates = List.of(
            query,
            query + " vol 1",
            query + " vol 2",
            query + " deluxe",
            query + " collector",
            query + " series",
            query + " author",
            query + " guide"
        );

        Map<String, String> deduped = new LinkedHashMap<>();
        for (String candidate : candidates) {
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
            }
            if (deduped.size() >= size) {
                break;
            }
        }

        List<AutocompleteResponse.Suggestion> suggestions = new ArrayList<>();
        int index = 0;
        for (String text : deduped.values()) {
            AutocompleteResponse.Suggestion suggestion = new AutocompleteResponse.Suggestion();
            suggestion.setText(text);
            suggestion.setScore(Math.max(SCORE_FLOOR, 1.0 - (SCORE_STEP * index)));
            suggestion.setSource(SOURCE);
            suggestions.add(suggestion);
            index += 1;
        }
        return suggestions;
    }
}
