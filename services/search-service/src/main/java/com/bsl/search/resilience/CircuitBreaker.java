package com.bsl.search.resilience;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class CircuitBreaker {
    private final int failureThreshold;
    private final long openDurationMs;
    private final AtomicInteger failureCount = new AtomicInteger(0);
    private final AtomicLong openUntilMs = new AtomicLong(0L);

    public CircuitBreaker(int failureThreshold, long openDurationMs) {
        this.failureThreshold = Math.max(1, failureThreshold);
        this.openDurationMs = Math.max(1L, openDurationMs);
    }

    public boolean allowRequest() {
        return System.currentTimeMillis() >= openUntilMs.get();
    }

    public boolean isOpen() {
        return !allowRequest();
    }

    public void recordSuccess() {
        failureCount.set(0);
    }

    public void recordFailure() {
        int failures = failureCount.incrementAndGet();
        if (failures >= failureThreshold) {
            openUntilMs.set(System.currentTimeMillis() + openDurationMs);
            failureCount.set(0);
        }
    }
}
