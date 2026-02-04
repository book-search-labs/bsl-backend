package com.bsl.ranking.service;

import java.util.Iterator;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class RerankScoreCache {
    private final RerankCacheProperties properties;
    private final ConcurrentHashMap<String, CacheEntry> entries = new ConcurrentHashMap<>();

    public RerankScoreCache(RerankCacheProperties properties) {
        this.properties = properties;
    }

    public Optional<Double> get(String key) {
        if (!properties.isEnabled() || key == null || key.isBlank()) {
            return Optional.empty();
        }
        CacheEntry entry = entries.get(key);
        if (entry == null) {
            return Optional.empty();
        }
        long now = System.currentTimeMillis();
        if (entry.expiresAtMs < now) {
            entries.remove(key);
            return Optional.empty();
        }
        return Optional.of(entry.score);
    }

    public void put(String key, double score) {
        if (!properties.isEnabled() || key == null || key.isBlank()) {
            return;
        }
        long ttlMs = Math.max(1L, properties.getTtlSeconds()) * 1000L;
        long expiresAtMs = System.currentTimeMillis() + ttlMs;
        entries.put(key, new CacheEntry(score, expiresAtMs));
        evictIfNeeded();
    }

    private void evictIfNeeded() {
        int maxEntries = Math.max(100, properties.getMaxEntries());
        if (entries.size() <= maxEntries) {
            return;
        }
        long now = System.currentTimeMillis();
        Iterator<Map.Entry<String, CacheEntry>> iterator = entries.entrySet().iterator();
        while (iterator.hasNext() && entries.size() > maxEntries) {
            Map.Entry<String, CacheEntry> entry = iterator.next();
            if (entry.getValue().expiresAtMs < now) {
                iterator.remove();
            }
        }
        if (entries.size() <= maxEntries) {
            return;
        }
        iterator = entries.entrySet().iterator();
        while (iterator.hasNext() && entries.size() > maxEntries) {
            iterator.next();
            iterator.remove();
        }
    }

    private record CacheEntry(double score, long expiresAtMs) {}
}
