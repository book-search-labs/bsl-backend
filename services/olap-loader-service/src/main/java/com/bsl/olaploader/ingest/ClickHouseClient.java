package com.bsl.olaploader.ingest;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ClickHouseClient {
    private static final Logger log = LoggerFactory.getLogger(ClickHouseClient.class);

    private final HttpClient httpClient;
    private final String baseUrl;
    private final String database;
    private final int requestTimeoutMs;

    public ClickHouseClient(String baseUrl, String database, int requestTimeoutMs) {
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.database = database;
        this.requestTimeoutMs = requestTimeoutMs;
        this.httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(Math.max(requestTimeoutMs, 500)))
            .build();
    }

    public void insert(String table, List<String> rows) {
        if (rows == null || rows.isEmpty()) {
            return;
        }
        String query = "INSERT INTO " + database + "." + table + " FORMAT JSONEachRow";
        String url = baseUrl + "/?query=" + urlEncode(query);
        String payload = String.join("\n", rows);

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(url))
            .timeout(Duration.ofMillis(Math.max(requestTimeoutMs, 500)))
            .POST(HttpRequest.BodyPublishers.ofString(payload))
            .build();

        try {
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() >= 400) {
                log.warn("ClickHouse insert failed table={} status={} body={}", table, response.statusCode(), response.body());
            }
        } catch (IOException | InterruptedException ex) {
            Thread.currentThread().interrupt();
            log.warn("ClickHouse insert error table={} error={}", table, ex.getMessage());
        }
    }

    private String urlEncode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }
}
