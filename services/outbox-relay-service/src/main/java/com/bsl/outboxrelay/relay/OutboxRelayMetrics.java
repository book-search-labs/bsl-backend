package com.bsl.outboxrelay.relay;

import java.util.concurrent.atomic.AtomicLong;

public class OutboxRelayMetrics {
    private final AtomicLong publishSuccess = new AtomicLong(0);
    private final AtomicLong publishFailure = new AtomicLong(0);

    public void incrementSuccess() {
        publishSuccess.incrementAndGet();
    }

    public void incrementFailure() {
        publishFailure.incrementAndGet();
    }

    public long getPublishSuccess() {
        return publishSuccess.get();
    }

    public long getPublishFailure() {
        return publishFailure.get();
    }

    public long getPublishTotal() {
        return publishSuccess.get() + publishFailure.get();
    }
}
