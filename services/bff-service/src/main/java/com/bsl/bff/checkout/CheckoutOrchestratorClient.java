package com.bsl.bff.checkout;

import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.common.DownstreamHeaders;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.config.DownstreamProperties;
import com.bsl.bff.security.AuthContext;
import com.bsl.bff.security.AuthContextHolder;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import org.springframework.beans.factory.annotation.Qualifier;
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
public class CheckoutOrchestratorClient {
    private final RestTemplate restTemplate;
    private final DownstreamProperties.ServiceProperties properties;
    private final ObjectMapper objectMapper;

    public CheckoutOrchestratorClient(
        @Qualifier("checkoutOrchestratorRestTemplate") RestTemplate restTemplate,
        DownstreamProperties downstreamProperties,
        ObjectMapper objectMapper
    ) {
        this.restTemplate = restTemplate;
        this.properties = downstreamProperties.getCheckoutOrchestratorService();
        this.objectMapper = objectMapper;
    }

    public ResponseEntity<String> exchange(
        HttpMethod method,
        String pathWithQuery,
        String body,
        RequestContext context,
        String idempotencyKey,
        String sessionId
    ) {
        HttpHeaders headers = DownstreamHeaders.from(context);
        headers.add(HttpHeaders.CONTENT_TYPE, "application/json");
        addIfPresent(headers, "Idempotency-Key", idempotencyKey);
        addIfPresent(headers, "x-session-id", sessionId);

        AuthContext auth = AuthContextHolder.get();
        if (auth != null) {
            addIfPresent(headers, "x-user-id", auth.getUserId());
            addIfPresent(headers, "x-admin-id", auth.getAdminId());
        }

        try {
            return restTemplate.exchange(buildUri(pathWithQuery), method, new HttpEntity<>(body, headers), String.class);
        } catch (ResourceAccessException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "checkout_orchestrator_timeout",
                "Checkout orchestrator timeout");
        } catch (HttpStatusCodeException ex) {
            HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
            if (status == null) {
                status = HttpStatus.SERVICE_UNAVAILABLE;
            }
            String defaultCode = status.is4xxClientError()
                ? "checkout_orchestrator_bad_request"
                : "checkout_orchestrator_error";
            DownstreamError error = parseDownstreamError(ex.getResponseBodyAsString(), defaultCode);
            throw new DownstreamException(status, error.code(), error.message());
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

    private void addIfPresent(HttpHeaders headers, String name, String value) {
        if (value != null && !value.isBlank()) {
            headers.add(name, value);
        }
    }

    private DownstreamError parseDownstreamError(String body, String defaultCode) {
        if (body == null || body.isBlank()) {
            return new DownstreamError(defaultCode, "요청 처리 중 오류가 발생했습니다.");
        }
        try {
            JsonNode root = objectMapper.readTree(body);
            JsonNode errorNode = root.path("error");
            String code = text(errorNode.get("code"));
            String message = text(errorNode.get("message"));
            if (code == null) {
                code = text(root.get("code"));
            }
            if (message == null) {
                message = text(root.get("message"));
            }
            return new DownstreamError(code == null ? defaultCode : code, message == null ? body.trim() : message);
        } catch (Exception ignored) {
            return new DownstreamError(defaultCode, body.trim());
        }
    }

    private String text(JsonNode node) {
        return node != null && node.isTextual() && !node.asText().isBlank() ? node.asText() : null;
    }

    private record DownstreamError(String code, String message) {
    }
}
