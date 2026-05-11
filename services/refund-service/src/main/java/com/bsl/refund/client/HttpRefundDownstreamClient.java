package com.bsl.refund.client;

import com.bsl.refund.config.RefundProperties;
import java.net.URI;
import java.util.Map;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

@Component
public class HttpRefundDownstreamClient implements RefundDownstreamClient {
    private final RestTemplate paymentRestTemplate;
    private final RestTemplate inventoryRestTemplate;
    private final RefundProperties properties;

    public HttpRefundDownstreamClient(
        @Qualifier("refundPaymentRestTemplate") RestTemplate paymentRestTemplate,
        @Qualifier("refundInventoryRestTemplate") RestTemplate inventoryRestTemplate,
        RefundProperties properties
    ) {
        this.paymentRestTemplate = paymentRestTemplate;
        this.inventoryRestTemplate = inventoryRestTemplate;
        this.properties = properties;
    }

    @Override
    public Map<String, Object> cancelPayment(Map<String, Object> request, String idempotencyKey, String traceId, String requestId) {
        return post(paymentRestTemplate, properties.getPaymentService().getBaseUrl(), "/internal/payments/cancel",
            request, idempotencyKey, traceId, requestId);
    }

    @Override
    public Optional<Map<String, Object>> findPaymentByIdempotencyKey(String idempotencyKey, String traceId, String requestId) {
        return get(paymentRestTemplate, properties.getPaymentService().getBaseUrl(),
            "/internal/payments/by-idempotency-key/" + idempotencyKey, traceId, requestId);
    }

    @Override
    public Map<String, Object> releaseInventory(Map<String, Object> request, String idempotencyKey, String traceId, String requestId) {
        return post(inventoryRestTemplate, properties.getInventoryService().getBaseUrl(), "/internal/inventory/release",
            request, idempotencyKey, traceId, requestId);
    }

    @Override
    public Optional<Map<String, Object>> findInventoryByIdempotencyKey(String idempotencyKey, String traceId, String requestId) {
        return get(inventoryRestTemplate, properties.getInventoryService().getBaseUrl(),
            "/internal/inventory/reservations/by-idempotency-key/" + idempotencyKey, traceId, requestId);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> post(
        RestTemplate restTemplate,
        String baseUrl,
        String path,
        Map<String, Object> request,
        String idempotencyKey,
        String traceId,
        String requestId
    ) {
        try {
            ResponseEntity<Map> response = restTemplate.exchange(
                uri(baseUrl, path),
                HttpMethod.POST,
                new HttpEntity<>(request, headers(idempotencyKey, traceId, requestId)),
                Map.class
            );
            return (Map<String, Object>) response.getBody();
        } catch (ResourceAccessException ex) {
            throw new DownstreamCallException("downstream timeout: " + path, true);
        } catch (HttpStatusCodeException ex) {
            throw new DownstreamCallException("downstream error: " + path + " status=" + ex.getStatusCode().value(), false);
        }
    }

    @SuppressWarnings("unchecked")
    private Optional<Map<String, Object>> get(
        RestTemplate restTemplate,
        String baseUrl,
        String path,
        String traceId,
        String requestId
    ) {
        try {
            ResponseEntity<Map> response = restTemplate.exchange(
                uri(baseUrl, path),
                HttpMethod.GET,
                new HttpEntity<>(headers(null, traceId, requestId)),
                Map.class
            );
            return Optional.ofNullable((Map<String, Object>) response.getBody());
        } catch (ResourceAccessException ex) {
            throw new DownstreamCallException("downstream timeout: " + path, true);
        } catch (HttpStatusCodeException ex) {
            return Optional.empty();
        }
    }

    private HttpHeaders headers(String idempotencyKey, String traceId, String requestId) {
        HttpHeaders headers = new HttpHeaders();
        headers.add(HttpHeaders.CONTENT_TYPE, "application/json");
        addIfPresent(headers, "Idempotency-Key", idempotencyKey);
        addIfPresent(headers, "x-trace-id", traceId);
        addIfPresent(headers, "x-request-id", requestId);
        return headers;
    }

    private void addIfPresent(HttpHeaders headers, String name, String value) {
        if (value != null && !value.isBlank()) {
            headers.add(name, value);
        }
    }

    private URI uri(String baseUrl, String path) {
        String normalizedBase = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        return URI.create(normalizedBase + path);
    }
}
