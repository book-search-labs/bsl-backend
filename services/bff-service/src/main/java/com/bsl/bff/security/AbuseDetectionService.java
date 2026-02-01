package com.bsl.bff.security;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class AbuseDetectionService {
    private final AbuseDetectionProperties properties;
    private final Map<String, Counter> counters = new ConcurrentHashMap<>();
    private final Map<String, Long> blockedUntil = new ConcurrentHashMap<>();

    public AbuseDetectionService(AbuseDetectionProperties properties) {
        this.properties = properties;
    }

    public boolean isEnabled() {
        return properties != null && properties.isEnabled();
    }

    public boolean isBlocked(String key) {
        Long until = blockedUntil.get(key);
        if (until == null) {
            return false;
        }
        if (System.currentTimeMillis() >= until) {
            blockedUntil.remove(key);
            return false;
        }
        return true;
    }

    public void recordError(String key) {
        if (!isEnabled()) {
            return;
        }
        Counter counter = counters.computeIfAbsent(key, k -> new Counter());
        int total = counter.increment(properties.getWindowSeconds());
        if (total >= properties.getErrorThreshold()) {
            long until = System.currentTimeMillis() + (properties.getBlockSeconds() * 1000L);
            blockedUntil.put(key, until);
            counter.reset();
        }
    }

    private static class Counter {
        private long windowStartMs = System.currentTimeMillis();
        private int count = 0;

        synchronized int increment(int windowSeconds) {
            long now = System.currentTimeMillis();
            long windowMs = windowSeconds * 1000L;
            if (now - windowStartMs > windowMs) {
                windowStartMs = now;
                count = 0;
            }
            count++;
            return count;
        }

        synchronized void reset() {
            count = 0;
            windowStartMs = System.currentTimeMillis();
        }
    }
}
