package com.bsl.bff.outbox;

public class OutboxEvent {
    private final String eventType;
    private final String aggregateType;
    private final String aggregateId;
    private final String dedupKey;
    private final String payloadJson;
    private final String status;

    public OutboxEvent(
        String eventType,
        String aggregateType,
        String aggregateId,
        String dedupKey,
        String payloadJson,
        String status
    ) {
        this.eventType = eventType;
        this.aggregateType = aggregateType;
        this.aggregateId = aggregateId;
        this.dedupKey = dedupKey;
        this.payloadJson = payloadJson;
        this.status = status;
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

    public String getStatus() {
        return status;
    }
}
