package com.bsl.bff.ratelimit;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class InMemoryRateLimiter implements RateLimiter {
    private final ConcurrentMap<String, Counter> counters = new ConcurrentHashMap<>();

    @Override
    public boolean tryAcquire(String key, int limit, int windowSeconds) {
        long windowId = System.currentTimeMillis() / 1000L / Math.max(windowSeconds, 1);
        Counter counter = counters.computeIfAbsent(key, k -> new Counter(windowId));
        synchronized (counter) {
            if (counter.windowId != windowId) {
                counter.windowId = windowId;
                counter.count = 0;
            }
            counter.count += 1;
            return counter.count <= limit;
        }
    }

    private static class Counter {
        private long windowId;
        private int count;

        private Counter(long windowId) {
            this.windowId = windowId;
        }
    }
}
