package com.bsl.search.cache;

import com.bsl.search.api.dto.SearchResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class SerpCacheService {
    private final SerpCacheProperties properties;
    private final ObjectMapper objectMapper;
    private final TtlCache<SearchResponse> cache;

    public SerpCacheService(SerpCacheProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.cache = new TtlCache<>(properties.getMaxEntries());
    }

    public boolean isEnabled() {
        return properties.isEnabled();
    }

    public Optional<CachedResponse> get(String key) {
        if (!properties.isEnabled() || key == null) {
            return Optional.empty();
        }
        return cache.get(key).map(entry -> new CachedResponse(entry.getValue(), entry.getCreatedAt(), entry.getExpiresAt()));
    }

    public void put(String key, SearchResponse response) {
        if (!properties.isEnabled() || key == null || response == null) {
            return;
        }
        cache.put(key, response, properties.getTtlMs());
    }

    public long getTtlMs() {
        return properties.getTtlMs();
    }

    public String buildKey(Map<String, Object> fields) {
        if (fields == null || fields.isEmpty()) {
            return null;
        }
        String hash = CacheKeyUtil.hashJson(objectMapper, fields);
        if (hash == null) {
            return null;
        }
        return properties.getKeyPrefix() + hash;
    }

    public Map<String, Object> baseKeyFields(
        String queryText,
        boolean lexicalEnabled,
        boolean vectorEnabled,
        int lexicalTopK,
        int vectorTopK,
        int rrfK,
        boolean rerankEnabled,
        int rerankTopK,
        int from,
        int size,
        Map<String, Double> boost,
        String operator,
        String minimumShouldMatch,
        List<Map<String, Object>> filters,
        List<String> fieldsOverride
    ) {
        Map<String, Object> fields = new HashMap<>();
        fields.put("q", queryText);
        fields.put("lexical", lexicalEnabled);
        fields.put("vector", vectorEnabled);
        fields.put("lexical_top_k", lexicalTopK);
        fields.put("vector_top_k", vectorTopK);
        fields.put("rrf_k", rrfK);
        fields.put("rerank", rerankEnabled);
        fields.put("rerank_top_k", rerankTopK);
        fields.put("from", from);
        fields.put("size", size);
        if (boost != null && !boost.isEmpty()) {
            fields.put("boost", boost);
        }
        if (operator != null) {
            fields.put("operator", operator);
        }
        if (minimumShouldMatch != null) {
            fields.put("minimum_should_match", minimumShouldMatch);
        }
        if (filters != null && !filters.isEmpty()) {
            fields.put("filters", filters);
        }
        if (fieldsOverride != null && !fieldsOverride.isEmpty()) {
            fields.put("fields", fieldsOverride);
        }
        return fields;
    }

    public static class CachedResponse {
        private final SearchResponse response;
        private final long createdAt;
        private final long expiresAt;

        public CachedResponse(SearchResponse response, long createdAt, long expiresAt) {
            this.response = response;
            this.createdAt = createdAt;
            this.expiresAt = expiresAt;
        }

        public SearchResponse getResponse() {
            return response;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public long getExpiresAt() {
            return expiresAt;
        }
    }
}
