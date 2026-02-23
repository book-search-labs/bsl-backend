package com.bsl.bff.client;

import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.common.DownstreamHeaders;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.config.DownstreamProperties;
import com.bsl.bff.security.AuthContext;
import com.bsl.bff.security.AuthContextHolder;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Component
public class QueryServiceClient {
    public static class ChatStreamResult {
        private String status = "ok";
        private final List<String> citations = new ArrayList<>();

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            if (status == null || status.isBlank()) {
                return;
            }
            this.status = status;
        }

        public List<String> getCitations() {
            return citations;
        }

        public void addCitation(String citation) {
            if (citation == null || citation.isBlank()) {
                return;
            }
            if (!citations.contains(citation)) {
                citations.add(citation);
            }
        }
    }

    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;
    private final DownstreamProperties.ServiceProperties properties;

    public QueryServiceClient(
        RestTemplate queryServiceRestTemplate,
        DownstreamProperties downstreamProperties,
        ObjectMapper objectMapper
    ) {
        this.restTemplate = queryServiceRestTemplate;
        this.properties = downstreamProperties.getQueryService();
        this.objectMapper = objectMapper;
    }

    public JsonNode fetchQueryContext(String rawQuery, RequestContext context) {
        String url = properties.getBaseUrl() + "/query/prepare";
        Map<String, Object> query = new HashMap<>();
        query.put("raw", rawQuery);
        Map<String, Object> body = new HashMap<>();
        body.put("query", query);

        HttpHeaders headers = DownstreamHeaders.from(context);
        enrichAuthHeaders(headers);
        headers.add(HttpHeaders.CONTENT_TYPE, "application/json");
        HttpEntity<Map<String, Object>> entity = new HttpEntity<>(body, headers);

        try {
            ResponseEntity<JsonNode> response = restTemplate.exchange(url, HttpMethod.POST, entity, JsonNode.class);
            return response.getBody();
        } catch (ResourceAccessException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "query_service_timeout", "Query service timeout");
        } catch (HttpStatusCodeException ex) {
            HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
            if (status == null) {
                status = HttpStatus.SERVICE_UNAVAILABLE;
            }
            throw new DownstreamException(status, "query_service_error", "Query service error");
        }
    }

    public JsonNode chat(Map<String, Object> body, RequestContext context) {
        String url = properties.getBaseUrl() + "/chat";
        HttpHeaders headers = DownstreamHeaders.from(context);
        enrichAuthHeaders(headers);
        headers.add(HttpHeaders.CONTENT_TYPE, "application/json");
        HttpEntity<Map<String, Object>> entity = new HttpEntity<>(body, headers);

        try {
            ResponseEntity<JsonNode> response = restTemplate.exchange(url, HttpMethod.POST, entity, JsonNode.class);
            return response.getBody();
        } catch (ResourceAccessException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "query_service_timeout", "Query service timeout");
        } catch (HttpStatusCodeException ex) {
            HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
            if (status == null) {
                status = HttpStatus.SERVICE_UNAVAILABLE;
            }
            throw new DownstreamException(status, "query_service_error", "Query service error");
        }
    }

    public ChatStreamResult chatStream(Map<String, Object> body, RequestContext context, SseEmitter emitter) {
        String url = properties.getBaseUrl() + "/chat?stream=true";
        HttpHeaders downstreamHeaders = DownstreamHeaders.from(context);
        enrichAuthHeaders(downstreamHeaders);
        downstreamHeaders.setContentType(MediaType.APPLICATION_JSON);
        downstreamHeaders.setAccept(java.util.List.of(MediaType.TEXT_EVENT_STREAM));
        ChatStreamResult result = new ChatStreamResult();

        try {
            restTemplate.execute(
                url,
                HttpMethod.POST,
                request -> {
                    request.getHeaders().putAll(downstreamHeaders);
                    objectMapper.writeValue(request.getBody(), body);
                },
                response -> {
                    streamSse(response.getBody(), emitter, result);
                    return null;
                }
            );
            return result;
        } catch (ResourceAccessException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "query_service_timeout", "Query service timeout");
        } catch (HttpStatusCodeException ex) {
            HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
            if (status == null) {
                status = HttpStatus.SERVICE_UNAVAILABLE;
            }
            throw new DownstreamException(status, "query_service_error", "Query service error");
        }
    }

    private void streamSse(InputStream bodyStream, SseEmitter emitter, ChatStreamResult result) throws IOException {
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(bodyStream, StandardCharsets.UTF_8))) {
            String eventName = "message";
            StringBuilder data = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isEmpty()) {
                    emitEvent(emitter, eventName, data, result);
                    eventName = "message";
                    data.setLength(0);
                    continue;
                }
                if (line.startsWith(":")) {
                    continue;
                }
                if (line.startsWith("event:")) {
                    eventName = line.substring("event:".length()).trim();
                    if (eventName.isEmpty()) {
                        eventName = "message";
                    }
                    continue;
                }
                if (line.startsWith("data:")) {
                    if (data.length() > 0) {
                        data.append('\n');
                    }
                    data.append(line.substring("data:".length()).trim());
                }
            }
            emitEvent(emitter, eventName, data, result);
        }
    }

    private void emitEvent(SseEmitter emitter, String eventName, StringBuilder data, ChatStreamResult result) throws IOException {
        if (data == null || data.length() == 0) {
            return;
        }
        String resolvedEvent = eventName == null || eventName.isBlank() ? "message" : eventName;
        String payload = data.toString();
        captureResult(resolvedEvent, payload, result);
        emitter.send(
            SseEmitter.event()
                .name(resolvedEvent)
                .data(payload, MediaType.TEXT_PLAIN)
        );
    }

    private void captureResult(String eventName, String payload, ChatStreamResult result) {
        if (result == null || payload == null || payload.isBlank()) {
            return;
        }
        if ("error".equals(eventName)) {
            result.setStatus("error");
            return;
        }
        if (!"done".equals(eventName)) {
            return;
        }
        try {
            JsonNode node = objectMapper.readTree(payload);
            JsonNode statusNode = node.get("status");
            if (statusNode != null && statusNode.isTextual()) {
                result.setStatus(statusNode.asText());
            }
            JsonNode citationsNode = node.get("citations");
            if (citationsNode != null && citationsNode.isArray()) {
                for (JsonNode citation : citationsNode) {
                    if (citation != null && citation.isTextual()) {
                        result.addCitation(citation.asText());
                    }
                }
            }
        } catch (Exception ignored) {
            // Keep stream passthrough best-effort even when done payload is non-JSON.
        }
    }

    private void enrichAuthHeaders(HttpHeaders headers) {
        AuthContext auth = AuthContextHolder.get();
        if (auth == null || headers == null) {
            return;
        }
        if (auth.getUserId() != null && !auth.getUserId().isBlank()) {
            headers.add("x-user-id", auth.getUserId());
        }
        if (auth.getAdminId() != null && !auth.getAdminId().isBlank()) {
            headers.add("x-admin-id", auth.getAdminId());
        }
    }
}
