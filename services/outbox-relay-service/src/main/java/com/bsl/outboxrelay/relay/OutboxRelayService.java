package com.bsl.outboxrelay.relay;

import com.bsl.outboxrelay.config.OutboxRelayProperties;
import com.bsl.outboxrelay.outbox.OutboxEvent;
import com.bsl.outboxrelay.outbox.OutboxEventRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

@Service
public class OutboxRelayService {
    private static final Logger logger = LoggerFactory.getLogger(OutboxRelayService.class);
    private static final long DEFAULT_SEND_TIMEOUT_MS = 5000;

    private final OutboxEventRepository repository;
    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;
    private final OutboxRelayProperties properties;
    private final OutboxRelayMetrics metrics = new OutboxRelayMetrics();
    private final AtomicReference<String> lastError = new AtomicReference<>(null);
    private final AtomicLong lastRunAt = new AtomicLong(0);

    public OutboxRelayService(
        OutboxEventRepository repository,
        KafkaTemplate<String, String> kafkaTemplate,
        ObjectMapper objectMapper,
        OutboxRelayProperties properties
    ) {
        this.repository = repository;
        this.kafkaTemplate = kafkaTemplate;
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    @Scheduled(fixedDelayString = "${outbox.relay.poll-interval-ms:1000}")
    public void relayBatch() {
        if (!properties.isEnabled()) {
            return;
        }
        lastRunAt.set(System.currentTimeMillis());
        List<OutboxEvent> events = repository.fetchNewEvents(properties.getBatchSize());
        if (events.isEmpty()) {
            return;
        }

        List<Long> sentIds = new ArrayList<>();
        List<Long> failedIds = new ArrayList<>();

        for (OutboxEvent event : events) {
            boolean ok = publishWithRetry(event);
            if (ok) {
                sentIds.add(event.getEventId());
            } else {
                failedIds.add(event.getEventId());
            }
        }

        repository.markSent(sentIds);
        repository.markFailed(failedIds);
    }

    public OutboxRelayMetrics getMetrics() {
        return metrics;
    }

    public String getLastError() {
        return lastError.get();
    }

    public long getLastRunAt() {
        return lastRunAt.get();
    }

    private boolean publishWithRetry(OutboxEvent event) {
        String topic = resolveTopic(event.getEventType());
        if (topic == null) {
            String message = "Missing topic mapping for event_type=" + event.getEventType();
            lastError.set(message);
            logger.warn(message);
            metrics.incrementFailure();
            return false;
        }

        String payload = buildEnvelope(event);
        if (payload == null) {
            String message = "Failed to serialize payload for event_id=" + event.getEventId();
            lastError.set(message);
            logger.warn(message);
            metrics.incrementFailure();
            return false;
        }

        int maxRetries = Math.max(1, properties.getMaxRetries());
        for (int attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                ProducerRecord<String, String> record = new ProducerRecord<>(topic, event.getDedupKey(), payload);
                addHeaders(record, event, topic, false, null);
                kafkaTemplate.send(record).get(DEFAULT_SEND_TIMEOUT_MS, TimeUnit.MILLISECONDS);
                metrics.incrementSuccess();
                return true;
            } catch (Exception ex) {
                lastError.set(ex.getMessage());
                logger.warn(
                    "Outbox publish failed event_id={} event_type={} attempt={}/{} error={}",
                    event.getEventId(),
                    event.getEventType(),
                    attempt,
                    maxRetries,
                    ex.getMessage()
                );
                if (attempt < maxRetries) {
                    backoff(attempt);
                }
            }
        }

        metrics.incrementFailure();
        if (properties.isDlqEnabled()) {
            publishToDlq(event, topic, lastError.get());
        }
        return false;
    }

    private void publishToDlq(OutboxEvent event, String topic, String error) {
        String dlqTopic = topic + properties.getDlqSuffix();
        String payload = buildDlqEnvelope(event, topic, error);
        if (payload == null) {
            logger.warn("Failed to serialize DLQ payload for event_id={}", event.getEventId());
            return;
        }
        try {
            ProducerRecord<String, String> record = new ProducerRecord<>(dlqTopic, event.getDedupKey(), payload);
            addHeaders(record, event, dlqTopic, true, error);
            kafkaTemplate.send(record).get(DEFAULT_SEND_TIMEOUT_MS, TimeUnit.MILLISECONDS);
            logger.warn("Routed event_id={} to DLQ topic={}", event.getEventId(), dlqTopic);
        } catch (Exception ex) {
            logger.warn(
                "Failed to publish DLQ event_id={} topic={} error={}",
                event.getEventId(),
                dlqTopic,
                ex.getMessage()
            );
        }
    }

    private void addHeaders(
        ProducerRecord<String, String> record,
        OutboxEvent event,
        String topic,
        boolean dlq,
        String error
    ) {
        List<Header> headers = new ArrayList<>();
        headers.add(new RecordHeader("event_type", bytes(event.getEventType())));
        headers.add(new RecordHeader("event_id", bytes(String.valueOf(event.getEventId()))));
        headers.add(new RecordHeader("dedup_key", bytes(event.getDedupKey())));
        headers.add(new RecordHeader("aggregate_type", bytes(event.getAggregateType())));
        headers.add(new RecordHeader("aggregate_id", bytes(event.getAggregateId())));
        headers.add(new RecordHeader("topic", bytes(topic)));
        if (dlq) {
            headers.add(new RecordHeader("dlq", bytes("true")));
        }
        if (error != null && !error.isBlank()) {
            headers.add(new RecordHeader("error", bytes(error)));
        }
        for (Header header : headers) {
            record.headers().add(header);
        }
    }

    private byte[] bytes(String value) {
        return value == null ? new byte[0] : value.getBytes(StandardCharsets.UTF_8);
    }

    private void backoff(int attempt) {
        long sleepMs = properties.getBackoffMs() * attempt;
        if (sleepMs <= 0) {
            return;
        }
        try {
            Thread.sleep(sleepMs);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    private String resolveTopic(String eventType) {
        Map<String, String> mapping = properties.getTopicMapping();
        if (mapping == null) {
            return null;
        }
        String topic = mapping.get(eventType);
        if (topic == null || topic.isBlank()) {
            return null;
        }
        return topic;
    }

    private String buildEnvelope(OutboxEvent event) {
        ObjectNode envelope = objectMapper.createObjectNode();
        envelope.put("schema_version", "v1");
        envelope.put("event_id", String.valueOf(event.getEventId()));
        envelope.put("event_type", event.getEventType());
        envelope.put("dedup_key", event.getDedupKey());
        envelope.put("occurred_at", DateTimeFormatter.ISO_INSTANT.format(event.getCreatedAt()));
        envelope.put("producer", properties.getProducerName());
        envelope.put("aggregate_type", event.getAggregateType());
        envelope.put("aggregate_id", event.getAggregateId());
        JsonNode payload = parsePayload(event.getPayloadJson());
        if (payload == null) {
            return null;
        }
        envelope.set("payload", payload);
        try {
            return objectMapper.writeValueAsString(envelope);
        } catch (JsonProcessingException ex) {
            logger.warn("Failed to serialize event envelope: {}", ex.getMessage());
            return null;
        }
    }

    private String buildDlqEnvelope(OutboxEvent event, String topic, String error) {
        ObjectNode envelope = objectMapper.createObjectNode();
        envelope.put("schema_version", "v1");
        envelope.put("event_id", String.valueOf(event.getEventId()));
        envelope.put("event_type", event.getEventType());
        envelope.put("dedup_key", event.getDedupKey());
        envelope.put("occurred_at", DateTimeFormatter.ISO_INSTANT.format(event.getCreatedAt()));
        envelope.put("failed_at", DateTimeFormatter.ISO_INSTANT.format(Instant.now()));
        envelope.put("producer", properties.getProducerName());
        envelope.put("aggregate_type", event.getAggregateType());
        envelope.put("aggregate_id", event.getAggregateId());
        envelope.put("original_topic", topic);
        if (error != null) {
            envelope.put("error", error);
        }
        JsonNode payload = parsePayload(event.getPayloadJson());
        if (payload == null) {
            return null;
        }
        envelope.set("payload", payload);
        try {
            return objectMapper.writeValueAsString(envelope);
        } catch (JsonProcessingException ex) {
            logger.warn("Failed to serialize DLQ envelope: {}", ex.getMessage());
            return null;
        }
    }

    private JsonNode parsePayload(String payloadJson) {
        if (payloadJson == null || payloadJson.isBlank()) {
            return null;
        }
        try {
            return objectMapper.readTree(payloadJson);
        } catch (JsonProcessingException ex) {
            logger.warn("Failed to parse payload json: {}", ex.getMessage());
            return null;
        }
    }
}
