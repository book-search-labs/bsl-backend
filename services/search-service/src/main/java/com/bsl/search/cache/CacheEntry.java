package com.bsl.search.cache;

public class CacheEntry<V> {
    private final V value;
    private final long createdAt;
    private final long expiresAt;

    public CacheEntry(V value, long createdAt, long expiresAt) {
        this.value = value;
        this.createdAt = createdAt;
        this.expiresAt = expiresAt;
    }

    public V getValue() {
        return value;
    }

    public long getCreatedAt() {
        return createdAt;
    }

    public long getExpiresAt() {
        return expiresAt;
    }

    public boolean isExpired() {
        return System.currentTimeMillis() > expiresAt;
    }
}
