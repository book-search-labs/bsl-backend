package com.bsl.bff.ops;

import com.bsl.bff.config.OpsMetricsProperties;
import com.bsl.bff.ops.dto.MetricsPointDto;
import com.bsl.bff.ops.dto.MetricsSummaryDto;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Repository;
import org.springframework.web.client.RestTemplate;

@Repository
public class MetricsOpsRepository {
    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;
    private final OpsMetricsProperties properties;

    public MetricsOpsRepository(
        RestTemplate metricsOpsRestTemplate,
        ObjectMapper objectMapper,
        OpsMetricsProperties properties
    ) {
        this.restTemplate = metricsOpsRestTemplate;
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    public MetricsSummaryDto fetchSummary(String windowValue) {
        Window window = Window.parse(windowValue);
        String sql =
            "SELECT "
                + "count() AS query_count, "
                + "toFloat64(if(count() = 0, 0, quantileTDigest(0.95)(took_ms))) AS p95_ms, "
                + "toFloat64(if(count() = 0, 0, quantileTDigest(0.99)(took_ms))) AS p99_ms, "
                + "toFloat64(if(count() = 0, 0, avg(toFloat64(zero_result)))) AS zero_result_rate, "
                + "toFloat64(if(count() = 0, 0, avg(toFloat64(rerank_applied)))) AS rerank_rate, "
                + "toFloat64(if(count() = 0, 0, avg(if(status = 'ok', 0.0, 1.0)))) AS error_rate "
                + "FROM " + table() + " "
                + "WHERE event_time >= now() - INTERVAL " + window.lookbackMinutes + " MINUTE "
                + "FORMAT JSON";
        JsonNode data = queryData(sql);
        MetricsSummaryDto summary = new MetricsSummaryDto();
        if (data.isArray() && !data.isEmpty()) {
            JsonNode row = data.get(0);
            summary.setQueryCount(asLong(row.get("query_count")));
            summary.setP95Ms(asDouble(row.get("p95_ms")));
            summary.setP99Ms(asDouble(row.get("p99_ms")));
            summary.setZeroResultRate(asDouble(row.get("zero_result_rate")));
            summary.setRerankRate(asDouble(row.get("rerank_rate")));
            summary.setErrorRate(asDouble(row.get("error_rate")));
        }
        return summary;
    }

    public List<MetricsPointDto> fetchTimeseries(String metricValue, String windowValue) {
        Metric metric = Metric.parse(metricValue);
        Window window = Window.parse(windowValue);
        String sql =
            "SELECT "
                + "formatDateTime(toStartOfInterval(event_time, INTERVAL " + window.bucketMinutes + " MINUTE), "
                + "'%Y-%m-%dT%H:%i:%sZ') AS ts, "
                + metric.expression + " AS value "
                + "FROM " + table() + " "
                + "WHERE event_time >= now() - INTERVAL " + window.lookbackMinutes + " MINUTE "
                + "GROUP BY ts "
                + "ORDER BY ts ASC "
                + "FORMAT JSON";
        JsonNode data = queryData(sql);
        List<MetricsPointDto> items = new ArrayList<>();
        if (data.isArray()) {
            for (JsonNode row : data) {
                MetricsPointDto point = new MetricsPointDto();
                point.setTs(row.path("ts").asText(""));
                point.setValue(asDouble(row.get("value")));
                items.add(point);
            }
        }
        return items;
    }

    public String normalizeMetric(String metricValue) {
        return Metric.parse(metricValue).key;
    }

    public boolean isEnabled() {
        return properties.isEnabled();
    }

    private JsonNode queryData(String sql) {
        String base = properties.getClickhouseUrl();
        if (base == null || base.isBlank()) {
            throw new IllegalStateException("clickhouse_url is required");
        }
        String encoded = URLEncoder.encode(sql, StandardCharsets.UTF_8);
        String url = trimTrailingSlash(base) + "/?query=" + encoded;
        try {
            ResponseEntity<String> response = restTemplate.exchange(
                url,
                HttpMethod.POST,
                HttpEntity.EMPTY,
                String.class
            );
            String body = response.getBody();
            if (body == null || body.isBlank()) {
                return objectMapper.createArrayNode();
            }
            JsonNode root = objectMapper.readTree(body);
            JsonNode data = root.get("data");
            return data == null ? objectMapper.createArrayNode() : data;
        } catch (Exception ex) {
            throw new IllegalStateException("metrics query failed", ex);
        }
    }

    private String table() {
        String database = properties.getClickhouseDatabase();
        if (database == null || database.isBlank()) {
            database = "bsl_olap";
        }
        return database + ".search_result_summary";
    }

    private String trimTrailingSlash(String value) {
        if (value == null) {
            return "";
        }
        if (value.endsWith("/")) {
            return value.substring(0, value.length() - 1);
        }
        return value;
    }

    private long asLong(JsonNode node) {
        if (node == null || node.isNull()) {
            return 0L;
        }
        return node.asLong(0L);
    }

    private double asDouble(JsonNode node) {
        if (node == null || node.isNull()) {
            return 0.0;
        }
        return node.asDouble(0.0);
    }

    private static class Window {
        private final int lookbackMinutes;
        private final int bucketMinutes;

        private Window(int lookbackMinutes, int bucketMinutes) {
            this.lookbackMinutes = lookbackMinutes;
            this.bucketMinutes = bucketMinutes;
        }

        private static Window parse(String raw) {
            if (raw == null) {
                return new Window(15, 1);
            }
            String normalized = raw.trim().toLowerCase();
            if ("1h".equals(normalized)) {
                return new Window(60, 5);
            }
            if ("24h".equals(normalized)) {
                return new Window(24 * 60, 60);
            }
            return new Window(15, 1);
        }
    }

    private static class Metric {
        private final String key;
        private final String expression;

        private Metric(String key, String expression) {
            this.key = key;
            this.expression = expression;
        }

        private static Metric parse(String raw) {
            if (raw == null) {
                return queryCount();
            }
            String normalized = raw.trim().toLowerCase();
            return switch (normalized) {
                case "p95", "p95_ms" -> new Metric("p95_ms", "toFloat64(quantileTDigest(0.95)(took_ms))");
                case "p99", "p99_ms" -> new Metric("p99_ms", "toFloat64(quantileTDigest(0.99)(took_ms))");
                case "zero_result", "zero_result_rate" -> new Metric(
                    "zero_result_rate",
                    "toFloat64(avg(toFloat64(zero_result)))"
                );
                case "rerank_rate" -> new Metric("rerank_rate", "toFloat64(avg(toFloat64(rerank_applied)))");
                case "error", "error_rate" -> new Metric("error_rate", "toFloat64(avg(if(status = 'ok', 0.0, 1.0)))");
                case "query_count", "queries" -> queryCount();
                default -> queryCount();
            };
        }

        private static Metric queryCount() {
            return new Metric("query_count", "toFloat64(count())");
        }
    }
}
