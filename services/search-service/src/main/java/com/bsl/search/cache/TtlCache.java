package com.bsl.search.cache;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;

public class TtlCache<V> {
    private final ConcurrentHashMap<String, CacheEntry<V>> entries = new ConcurrentHashMap<>();
    private final ConcurrentLinkedQueue<String> order = new ConcurrentLinkedQueue<>();
    private final int maxEntries;

    public TtlCache(int maxEntries) {
        this.maxEntries = Math.max(1, maxEntries);
    }

    public Optional<CacheEntry<V>> get(String key) {
        if (key == null) {
            return Optional.empty();
        }
        CacheEntry<V> entry = entries.get(key);
        if (entry == null) {
            return Optional.empty();
        }
        if (entry.isExpired()) {
            entries.remove(key);
            return Optional.empty();
        }
        return Optional.of(entry);
    }

    public void put(String key, V value, long ttlMs) {
        if (key == null || value == null || ttlMs <= 0) {
            return;
        }
        long now = System.currentTimeMillis();
        CacheEntry<V> entry = new CacheEntry<>(value, now, now + ttlMs);
        entries.put(key, entry);
        order.add(key);
        evictIfNeeded();
    }

    private void evictIfNeeded() {
        while (entries.size() > maxEntries) {
            String key = order.poll();
            if (key == null) {
                break;
            }
            entries.remove(key);
        }
    }
}
