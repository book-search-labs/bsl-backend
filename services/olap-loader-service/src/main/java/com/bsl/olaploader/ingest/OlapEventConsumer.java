package com.bsl.olaploader.ingest;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OlapEventConsumer {
    private static final Logger log = LoggerFactory.getLogger(OlapEventConsumer.class);
    private static final DateTimeFormatter DATE_FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd");
    private static final DateTimeFormatter DATETIME_FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final ObjectMapper objectMapper;
    private final ClickHouseBatchWriter writer;

    public OlapEventConsumer(ObjectMapper objectMapper, ClickHouseBatchWriter writer) {
        this.objectMapper = objectMapper;
        this.writer = writer;
    }

    @KafkaListener(
        topics = {
            "${olap.topics.search-impression:search_impression_v1}",
            "${olap.topics.search-click:search_click_v1}",
            "${olap.topics.search-dwell:search_dwell_v1}",
            "${olap.topics.ac-impression:ac_impression_v1}",
            "${olap.topics.ac-select:ac_select_v1}"
        }
    )
    public void consume(String message) {
        if (message == null || message.isBlank()) {
            return;
        }
        try {
            JsonNode root = objectMapper.readTree(message);
            String eventType = root.path("event_type").asText(null);
            String eventId = root.path("event_id").asText("");
            String dedupKey = root.path("dedup_key").asText("");
            String occurredAt = root.path("occurred_at").asText(null);
            JsonNode payload = root.get("payload");
            if (eventType == null || payload == null || payload.isNull()) {
                return;
            }

            switch (eventType) {
                case "search_impression" -> writer.append(
                    "search_impression",
                    buildSearchImpression(payload, eventId, dedupKey, occurredAt)
                );
                case "search_click" -> writer.append(
                    "search_click",
                    buildSearchClick(payload, eventId, dedupKey, occurredAt)
                );
                case "search_dwell" -> writer.append(
                    "search_dwell",
                    buildSearchDwell(payload, eventId, dedupKey, occurredAt)
                );
                case "ac_impression" -> writer.append(
                    "ac_impression",
                    buildAcImpression(payload, eventId, dedupKey, occurredAt)
                );
                case "ac_select" -> writer.append(
                    "ac_select",
                    buildAcSelect(payload, eventId, dedupKey, occurredAt)
                );
                default -> {
                    // ignore
                }
            }
        } catch (Exception ex) {
            log.warn("Failed to parse OLAP event: {}", ex.getMessage());
        }
    }

    private List<Map<String, Object>> buildSearchImpression(
        JsonNode payload,
        String eventId,
        String dedupKey,
        String occurredAt
    ) {
        List<Map<String, Object>> rows = new ArrayList<>();
        String eventTime = resolveEventTime(payload, occurredAt);
        String eventDate = toDate(eventTime);
        JsonNode results = payload.get("results");
        if (results == null || !results.isArray()) {
            return rows;
        }
        for (JsonNode entry : results) {
            if (entry == null || entry.isNull()) {
                continue;
            }
            String docId = entry.path("doc_id").asText("");
            if (docId.isBlank()) {
                continue;
            }
            Map<String, Object> row = baseRow(payload, eventId, dedupKey, eventDate, eventTime);
            row.put("imp_id", payload.path("imp_id").asText(""));
            row.put("doc_id", docId);
            row.put("position", entry.path("position").asInt(0));
            row.put("query_hash", payload.path("query_hash").asText(null));
            row.put("query_raw", payload.path("query_raw").asText(null));
            row.put("policy_id", payload.path("policy_id").asText(null));
            row.put("experiment_id", payload.path("experiment_id").asText(null));
            row.put("experiment_bucket", payload.path("experiment_bucket").asText(null));
            rows.add(row);
        }
        return rows;
    }

    private List<Map<String, Object>> buildSearchClick(
        JsonNode payload,
        String eventId,
        String dedupKey,
        String occurredAt
    ) {
        String eventTime = resolveEventTime(payload, occurredAt);
        String eventDate = toDate(eventTime);
        String docId = payload.path("doc_id").asText("");
        if (docId.isBlank()) {
            return List.of();
        }
        Map<String, Object> row = baseRow(payload, eventId, dedupKey, eventDate, eventTime);
        row.put("imp_id", payload.path("imp_id").asText(""));
        row.put("doc_id", docId);
        row.put("position", payload.path("position").asInt(0));
        row.put("query_hash", payload.path("query_hash").asText(null));
        row.put("policy_id", payload.path("policy_id").asText(null));
        row.put("experiment_id", payload.path("experiment_id").asText(null));
        row.put("experiment_bucket", payload.path("experiment_bucket").asText(null));
        return List.of(row);
    }

    private List<Map<String, Object>> buildSearchDwell(
        JsonNode payload,
        String eventId,
        String dedupKey,
        String occurredAt
    ) {
        String eventTime = resolveEventTime(payload, occurredAt);
        String eventDate = toDate(eventTime);
        String docId = payload.path("doc_id").asText("");
        if (docId.isBlank()) {
            return List.of();
        }
        Map<String, Object> row = baseRow(payload, eventId, dedupKey, eventDate, eventTime);
        row.put("imp_id", payload.path("imp_id").asText(""));
        row.put("doc_id", docId);
        row.put("position", payload.path("position").asInt(0));
        row.put("dwell_ms", payload.path("dwell_ms").asInt(0));
        row.put("query_hash", payload.path("query_hash").asText(null));
        row.put("policy_id", payload.path("policy_id").asText(null));
        row.put("experiment_id", payload.path("experiment_id").asText(null));
        row.put("experiment_bucket", payload.path("experiment_bucket").asText(null));
        return List.of(row);
    }

    private List<Map<String, Object>> buildAcImpression(
        JsonNode payload,
        String eventId,
        String dedupKey,
        String occurredAt
    ) {
        List<Map<String, Object>> rows = new ArrayList<>();
        String eventTime = resolveEventTime(payload, occurredAt);
        String eventDate = toDate(eventTime);
        JsonNode suggestions = payload.get("suggestions");
        if (suggestions == null || !suggestions.isArray()) {
            return rows;
        }
        for (JsonNode entry : suggestions) {
            if (entry == null || entry.isNull()) {
                continue;
            }
            Map<String, Object> row = baseRow(payload, eventId, dedupKey, eventDate, eventTime);
            row.put("q", payload.path("q").asText(""));
            row.put("size", payload.path("size").asInt(0));
            row.put("count", payload.path("count").asInt(0));
            row.put("text", entry.path("text").asText(""));
            row.put("position", entry.path("position").asInt(0));
            row.put("suggest_id", entry.path("suggest_id").asText(null));
            row.put("type", entry.path("type").asText(null));
            row.put("source", entry.path("source").asText(null));
            row.put("target_id", entry.path("target_id").asText(null));
            row.put("target_doc_id", entry.path("target_doc_id").asText(null));
            rows.add(row);
        }
        return rows;
    }

    private List<Map<String, Object>> buildAcSelect(
        JsonNode payload,
        String eventId,
        String dedupKey,
        String occurredAt
    ) {
        String eventTime = resolveEventTime(payload, occurredAt);
        String eventDate = toDate(eventTime);
        Map<String, Object> row = baseRow(payload, eventId, dedupKey, eventDate, eventTime);
        row.put("q", payload.path("q").asText(""));
        row.put("text", payload.path("text").asText(""));
        row.put("position", payload.path("position").asInt(0));
        row.put("suggest_id", payload.path("suggest_id").asText(null));
        row.put("type", payload.path("type").asText(null));
        row.put("source", payload.path("source").asText(null));
        row.put("target_id", payload.path("target_id").asText(null));
        row.put("target_doc_id", payload.path("target_doc_id").asText(null));
        return List.of(row);
    }

    private Map<String, Object> baseRow(
        JsonNode payload,
        String eventId,
        String dedupKey,
        String eventDate,
        String eventTime
    ) {
        Map<String, Object> row = new HashMap<>();
        row.put("event_date", eventDate);
        row.put("event_time", eventTime);
        row.put("event_id", eventId);
        row.put("dedup_key", dedupKey);
        row.put("request_id", payload.path("request_id").asText(""));
        row.put("trace_id", payload.path("trace_id").asText(""));
        row.put("session_id", payload.path("session_id").asText(null));
        row.put("user_id_hash", payload.path("user_id_hash").asText(null));
        return row;
    }

    private String resolveEventTime(JsonNode payload, String occurredAt) {
        String candidate = payload.path("event_time").asText(null);
        if (candidate == null || candidate.isBlank()) {
            candidate = occurredAt;
        }
        if (candidate == null || candidate.isBlank()) {
            return formatDateTime(OffsetDateTime.now());
        }
        try {
            return formatDateTime(OffsetDateTime.parse(candidate));
        } catch (Exception ex) {
            return formatDateTime(OffsetDateTime.now());
        }
    }

    private String toDate(String eventTime) {
        if (eventTime != null && eventTime.length() >= 10) {
            return eventTime.substring(0, 10);
        }
        return OffsetDateTime.now().format(DATE_FMT);
    }

    private String formatDateTime(OffsetDateTime time) {
        return time.format(DATETIME_FMT);
    }
}
