package com.bsl.bff.client;

import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.common.DownstreamHeaders;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.config.DownstreamProperties;
import com.bsl.bff.security.AuthContext;
import com.bsl.bff.security.AuthContextHolder;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

@Component
public class CommerceServiceClient {
    private final RestTemplate restTemplate;
    private final DownstreamProperties.ServiceProperties properties;
    private final ObjectMapper objectMapper;

    public CommerceServiceClient(
        RestTemplate commerceServiceRestTemplate,
        DownstreamProperties downstreamProperties,
        ObjectMapper objectMapper
    ) {
        this.restTemplate = commerceServiceRestTemplate;
        this.properties = downstreamProperties.getCommerceService();
        this.objectMapper = objectMapper;
    }

    public ResponseEntity<String> exchange(HttpMethod method, String pathWithQuery, String body, RequestContext context) {
        URI uri = buildUri(pathWithQuery);
        HttpHeaders headers = DownstreamHeaders.from(context);
        headers.add(HttpHeaders.CONTENT_TYPE, "application/json");

        AuthContext auth = AuthContextHolder.get();
        if (auth != null) {
            if (auth.getUserId() != null) {
                headers.add("x-user-id", auth.getUserId());
            }
            if (auth.getAdminId() != null) {
                headers.add("x-admin-id", auth.getAdminId());
            }
        }

        HttpEntity<String> entity = new HttpEntity<>(body, headers);
        try {
            return restTemplate.exchange(uri, method, entity, String.class);
        } catch (ResourceAccessException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "commerce_service_timeout",
                "Commerce service timeout");
        } catch (HttpStatusCodeException ex) {
            HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
            if (status == null) {
                status = HttpStatus.SERVICE_UNAVAILABLE;
            }
            String defaultCode = status.is4xxClientError() ? "commerce_service_bad_request" : "commerce_service_error";
            DownstreamError downstreamError = parseDownstreamError(ex.getResponseBodyAsString(), defaultCode);
            throw new DownstreamException(status, downstreamError.code(), downstreamError.message());
        }
    }

    private URI buildUri(String pathWithQuery) {
        String baseUrl = properties.getBaseUrl();
        String normalizedPath = pathWithQuery == null ? "" : pathWithQuery.trim();
        if (normalizedPath.isEmpty()) {
            normalizedPath = "/";
        } else if (!normalizedPath.startsWith("/")) {
            normalizedPath = "/" + normalizedPath;
        }

        if (baseUrl.endsWith("/") && normalizedPath.startsWith("/")) {
            baseUrl = baseUrl.substring(0, baseUrl.length() - 1);
        }
        return URI.create(baseUrl + normalizedPath);
    }

    private DownstreamError parseDownstreamError(String body, String defaultCode) {
        if (body == null || body.isBlank()) {
            return new DownstreamError(defaultCode, "요청 처리 중 오류가 발생했습니다.");
        }
        try {
            JsonNode root = objectMapper.readTree(body);
            JsonNode errorNode = root.path("error");
            String code = null;
            String message = null;
            if (!errorNode.isMissingNode() && errorNode.isObject()) {
                JsonNode codeNode = errorNode.get("code");
                JsonNode messageNode = errorNode.get("message");
                if (codeNode != null && codeNode.isTextual()) {
                    code = codeNode.asText();
                }
                if (messageNode != null && messageNode.isTextual()) {
                    message = messageNode.asText();
                }
            }
            if ((code == null || code.isBlank()) && root.has("code") && root.get("code").isTextual()) {
                code = root.get("code").asText();
            }
            if ((message == null || message.isBlank()) && root.has("message") && root.get("message").isTextual()) {
                message = root.get("message").asText();
            }
            if (code == null || code.isBlank()) {
                code = defaultCode;
            }
            if (message == null || message.isBlank()) {
                message = extractPlainMessage(body);
            }
            return new DownstreamError(code, message);
        } catch (Exception ignored) {
            return new DownstreamError(defaultCode, extractPlainMessage(body));
        }
    }

    private String extractPlainMessage(String body) {
        if (body == null) {
            return "요청 처리 중 오류가 발생했습니다.";
        }
        String trimmed = body.trim();
        if (trimmed.isEmpty()) {
            return "요청 처리 중 오류가 발생했습니다.";
        }
        String lower = trimmed.toLowerCase();
        if (lower.startsWith("<!doctype") || lower.startsWith("<html")) {
            return "요청 처리 중 오류가 발생했습니다.";
        }
        return trimmed;
    }

    private record DownstreamError(String code, String message) {
    }
}
