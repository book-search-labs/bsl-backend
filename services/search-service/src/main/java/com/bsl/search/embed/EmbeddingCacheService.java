package com.bsl.search.embed;

import com.bsl.search.cache.CacheKeyUtil;
import com.bsl.search.cache.TtlCache;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class EmbeddingCacheService {
    private final EmbeddingProperties properties;
    private final TtlCache<List<Double>> cache;

    public EmbeddingCacheService(EmbeddingProperties properties) {
        this.properties = properties;
        int maxEntries = properties.getCache() == null ? 2000 : properties.getCache().getMaxEntries();
        this.cache = new TtlCache<>(maxEntries);
    }

    public Optional<List<Double>> get(String text) {
        String key = buildKey(text);
        if (key == null) {
            return Optional.empty();
        }
        return cache.get(key).map(entry -> entry.getValue());
    }

    public void put(String text, List<Double> vector) {
        String key = buildKey(text);
        if (key == null || vector == null || vector.isEmpty()) {
            return;
        }
        long ttlMs = properties.getCache() == null ? 0L : properties.getCache().getTtlMs();
        cache.put(key, vector, ttlMs);
    }

    public boolean isEnabled() {
        return properties.getCache() != null && properties.getCache().isEnabled();
    }

    public String normalize(String text) {
        if (text == null) {
            return null;
        }
        String value = text.trim();
        if (properties.getCache() != null && properties.getCache().isNormalize()) {
            value = value.toLowerCase(Locale.ROOT);
        }
        return value;
    }

    private String buildKey(String text) {
        if (!isEnabled() || text == null) {
            return null;
        }
        String normalized = normalize(text);
        if (normalized == null || normalized.isBlank()) {
            return null;
        }
        int maxLen = properties.getCache() == null ? 0 : properties.getCache().getMaxTextLength();
        if (maxLen > 0 && normalized.length() > maxLen) {
            return null;
        }
        String model = properties.getModel() == null ? "" : properties.getModel();
        String mode = properties.getMode() == null ? "" : properties.getMode().name();
        String hash = CacheKeyUtil.sha256(normalized);
        return "embed:" + mode + ":" + model + ":" + hash;
    }
}
