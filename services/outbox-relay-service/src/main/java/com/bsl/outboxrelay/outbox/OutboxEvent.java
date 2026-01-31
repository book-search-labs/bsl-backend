package com.bsl.outboxrelay.outbox;

import java.time.Instant;

public class OutboxEvent {
    private final long eventId;
    private final String eventType;
    private final String aggregateType;
    private final String aggregateId;
    private final String dedupKey;
    private final String payloadJson;
    private final Instant createdAt;

    public OutboxEvent(
        long eventId,
        String eventType,
        String aggregateType,
        String aggregateId,
        String dedupKey,
        String payloadJson,
        Instant createdAt
    ) {
        this.eventId = eventId;
        this.eventType = eventType;
        this.aggregateType = aggregateType;
        this.aggregateId = aggregateId;
        this.dedupKey = dedupKey;
        this.payloadJson = payloadJson;
        this.createdAt = createdAt;
    }

    public long getEventId() {
        return eventId;
    }

    public String getEventType() {
        return eventType;
    }

    public String getAggregateType() {
        return aggregateType;
    }

    public String getAggregateId() {
        return aggregateId;
    }

    public String getDedupKey() {
        return dedupKey;
    }

    public String getPayloadJson() {
        return payloadJson;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
