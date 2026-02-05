package com.bsl.olaploader.ingest;

import com.bsl.olaploader.config.OlapLoaderProperties;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ClickHouseBatchWriter {
    private static final Logger log = LoggerFactory.getLogger(ClickHouseBatchWriter.class);

    private final ClickHouseClient client;
    private final ObjectMapper objectMapper;
    private final int batchSize;
    private final Map<String, List<String>> buffers = new ConcurrentHashMap<>();

    public ClickHouseBatchWriter(OlapLoaderProperties properties, ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
        this.batchSize = Math.max(1, properties.getBatchSize());
        this.client = new ClickHouseClient(
            properties.getBaseUrl(),
            properties.getDatabase(),
            properties.getRequestTimeoutMs()
        );
    }

    public void append(String table, List<Map<String, Object>> rows) {
        if (rows == null || rows.isEmpty()) {
            return;
        }
        List<String> buffer = buffers.computeIfAbsent(table, key -> new ArrayList<>());
        synchronized (buffer) {
            for (Map<String, Object> row : rows) {
                String json = toJson(row);
                if (json != null) {
                    buffer.add(json);
                }
            }
            if (buffer.size() >= batchSize) {
                flush(table, buffer);
            }
        }
    }

    @Scheduled(fixedDelayString = "${olap.clickhouse.flush-interval-ms:1000}")
    public void flushAll() {
        for (Map.Entry<String, List<String>> entry : buffers.entrySet()) {
            List<String> buffer = entry.getValue();
            synchronized (buffer) {
                if (!buffer.isEmpty()) {
                    flush(entry.getKey(), buffer);
                }
            }
        }
    }

    private void flush(String table, List<String> buffer) {
        if (buffer.isEmpty()) {
            return;
        }
        List<String> batch = new ArrayList<>(buffer);
        buffer.clear();
        client.insert(table, batch);
        log.debug("ClickHouse flush table={} rows={}", table, batch.size());
    }

    private String toJson(Map<String, Object> row) {
        try {
            return objectMapper.writeValueAsString(row);
        } catch (JsonProcessingException ex) {
            log.warn("Failed to serialize row for ClickHouse: {}", ex.getMessage());
            return null;
        }
    }
}
