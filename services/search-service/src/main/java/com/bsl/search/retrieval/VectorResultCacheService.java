package com.bsl.search.retrieval;

import com.bsl.search.cache.CacheKeyUtil;
import com.bsl.search.cache.TtlCache;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class VectorResultCacheService {
    private final VectorSearchProperties properties;
    private final ObjectMapper objectMapper;
    private final TtlCache<Entry> cache;

    public VectorResultCacheService(VectorSearchProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
        int maxEntries = properties.getCache() == null ? 2000 : properties.getCache().getMaxEntries();
        this.cache = new TtlCache<>(maxEntries);
    }

    public Optional<Entry> get(RetrievalStageContext context, String mode, String modelId) {
        String key = buildKey(context, mode, modelId);
        if (key == null) {
            return Optional.empty();
        }
        return cache.get(key).map(entry -> entry.getValue());
    }

    public void put(RetrievalStageContext context, String mode, String modelId, List<String> docIds, Object queryDsl) {
        String key = buildKey(context, mode, modelId);
        if (key == null || docIds == null) {
            return;
        }
        long ttlMs = properties.getCache() == null ? 0L : properties.getCache().getTtlMs();
        cache.put(key, new Entry(docIds, queryDsl), ttlMs);
    }

    private String buildKey(RetrievalStageContext context, String mode, String modelId) {
        if (!isEnabled(context)) {
            return null;
        }
        if (context == null || context.getQueryText() == null) {
            return null;
        }
        String query = normalize(context.getQueryText());
        if (query == null || query.isBlank()) {
            return null;
        }
        int maxLen = properties.getCache() == null ? 0 : properties.getCache().getMaxTextLength();
        if (maxLen > 0 && query.length() > maxLen) {
            return null;
        }
        Map<String, Object> keyFields = new HashMap<>();
        keyFields.put("q", query);
        keyFields.put("top_k", context.getTopK());
        keyFields.put("filters", context.getFilters());
        keyFields.put("mode", mode);
        keyFields.put("model", modelId);
        String hash = CacheKeyUtil.hashJson(objectMapper, keyFields);
        if (hash == null) {
            return null;
        }
        return "vec:" + hash;
    }

    private boolean isEnabled(RetrievalStageContext context) {
        if (properties.getCache() == null || !properties.getCache().isEnabled()) {
            return false;
        }
        if (context == null) {
            return false;
        }
        if (!properties.getCache().isCacheDebug()) {
            if (context.isDebug() || context.isExplain()) {
                return false;
            }
        }
        return true;
    }

    private String normalize(String text) {
        if (text == null) {
            return null;
        }
        String value = text.trim();
        if (properties.getCache() != null && properties.getCache().isNormalize()) {
            value = value.toLowerCase(Locale.ROOT);
        }
        return value;
    }

    public static class Entry {
        private final List<String> docIds;
        private final Object queryDsl;

        public Entry(List<String> docIds, Object queryDsl) {
            this.docIds = docIds;
            this.queryDsl = queryDsl;
        }

        public List<String> getDocIds() {
            return docIds;
        }

        public Object getQueryDsl() {
            return queryDsl;
        }
    }
}
