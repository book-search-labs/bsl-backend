package com.bsl.checkoutorchestrator.client;

import com.bsl.checkoutorchestrator.config.CheckoutOrchestratorProperties;
import com.bsl.checkoutorchestrator.domain.CheckoutStepName;
import java.net.URI;
import java.util.Map;
import java.util.Optional;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;

@Component
public class HttpCheckoutDownstreamClient implements CheckoutDownstreamClient {
    private final RestTemplate restTemplate;
    private final CheckoutOrchestratorProperties properties;

    public HttpCheckoutDownstreamClient(RestTemplate checkoutDownstreamRestTemplate, CheckoutOrchestratorProperties properties) {
        this.restTemplate = checkoutDownstreamRestTemplate;
        this.properties = properties;
    }

    @Override
    public Map<String, Object> execute(
        CheckoutStepName stepName,
        Map<String, Object> request,
        String idempotencyKey,
        String traceId,
        String requestId
    ) {
        URI uri = URI.create(baseUrl(stepName) + commandPath(stepName));
        try {
            ResponseEntity<Map> response = restTemplate.exchange(
                uri,
                HttpMethod.POST,
                new HttpEntity<>(request, headers(idempotencyKey, traceId, requestId)),
                Map.class
            );
            @SuppressWarnings("unchecked")
            Map<String, Object> body = (Map<String, Object>) response.getBody();
            return body == null ? Map.of() : body;
        } catch (ResourceAccessException ex) {
            throw new DownstreamCallException("downstream_timeout", "downstream timeout: " + stepName, true, true);
        } catch (HttpStatusCodeException ex) {
            boolean retryable = ex.getStatusCode().is5xxServerError();
            throw new DownstreamCallException(
                "downstream_http_" + ex.getStatusCode().value(),
                "downstream HTTP error " + ex.getStatusCode().value() + ": " + stepName,
                false,
                retryable
            );
        }
    }

    @Override
    public Optional<Map<String, Object>> reconcile(
        CheckoutStepName stepName,
        String idempotencyKey,
        String traceId,
        String requestId
    ) {
        String path = reconcilePath(stepName, idempotencyKey);
        if (path == null) {
            return Optional.empty();
        }
        URI uri = URI.create(baseUrl(stepName) + path);
        try {
            ResponseEntity<Map> response = restTemplate.exchange(
                uri,
                HttpMethod.GET,
                new HttpEntity<>(headers(null, traceId, requestId)),
                Map.class
            );
            @SuppressWarnings("unchecked")
            Map<String, Object> body = (Map<String, Object>) response.getBody();
            return Optional.ofNullable(body);
        } catch (ResourceAccessException ex) {
            throw new DownstreamCallException("downstream_timeout", "downstream reconciliation timeout: " + stepName, true, true);
        } catch (HttpStatusCodeException ex) {
            if (ex.getStatusCode().is4xxClientError()) {
                return Optional.empty();
            }
            throw new DownstreamCallException(
                "downstream_reconcile_http_" + ex.getStatusCode().value(),
                "downstream reconciliation HTTP error " + ex.getStatusCode().value() + ": " + stepName,
                false,
                true
            );
        }
    }

    @Override
    public Map<String, Object> compensate(
        CheckoutStepName stepName,
        Map<String, Object> request,
        String idempotencyKey,
        String traceId,
        String requestId
    ) {
        String path = compensationPath(stepName);
        if (path == null) {
            return Map.of("status", "SKIPPED", "step_name", stepName.name());
        }
        URI uri = URI.create(baseUrl(stepName) + path);
        try {
            ResponseEntity<Map> response = restTemplate.exchange(
                uri,
                HttpMethod.POST,
                new HttpEntity<>(request, headers(idempotencyKey, traceId, requestId)),
                Map.class
            );
            @SuppressWarnings("unchecked")
            Map<String, Object> body = (Map<String, Object>) response.getBody();
            return body == null ? Map.of() : body;
        } catch (ResourceAccessException ex) {
            throw new DownstreamCallException("compensation_timeout", "compensation timeout: " + stepName, true, true);
        } catch (HttpStatusCodeException ex) {
            boolean retryable = ex.getStatusCode().is5xxServerError();
            throw new DownstreamCallException(
                "compensation_http_" + ex.getStatusCode().value(),
                "compensation HTTP error " + ex.getStatusCode().value() + ": " + stepName,
                false,
                retryable
            );
        }
    }

    private String baseUrl(CheckoutStepName stepName) {
        return switch (stepName) {
            case CREATE_ORDER -> properties.getDownstream().getOrderService().getBaseUrl();
            case RESERVE_STOCK -> properties.getDownstream().getInventoryService().getBaseUrl();
            case AUTHORIZE_PAYMENT -> properties.getDownstream().getPaymentService().getBaseUrl();
            case REQUEST_SHIPMENT -> properties.getDownstream().getShipmentService().getBaseUrl();
        };
    }

    private String commandPath(CheckoutStepName stepName) {
        return switch (stepName) {
            case CREATE_ORDER -> "/internal/orders";
            case RESERVE_STOCK -> "/internal/inventory/reserve";
            case AUTHORIZE_PAYMENT -> "/internal/payments/authorize";
            case REQUEST_SHIPMENT -> "/internal/shipments";
        };
    }

    private String reconcilePath(CheckoutStepName stepName, String idempotencyKey) {
        String encoded = UriComponentsBuilder.fromPath("/{idempotencyKey}")
            .buildAndExpand(idempotencyKey)
            .encode()
            .toUriString();
        return switch (stepName) {
            case CREATE_ORDER -> null;
            case RESERVE_STOCK -> "/internal/inventory/reservations/by-idempotency-key" + encoded;
            case AUTHORIZE_PAYMENT -> "/internal/payments/by-idempotency-key" + encoded;
            case REQUEST_SHIPMENT -> "/internal/shipments/by-idempotency-key" + encoded;
        };
    }

    private String compensationPath(CheckoutStepName stepName) {
        return switch (stepName) {
            case CREATE_ORDER -> null;
            case RESERVE_STOCK -> "/internal/inventory/release";
            case AUTHORIZE_PAYMENT -> "/internal/payments/cancel";
            case REQUEST_SHIPMENT -> "/internal/shipments/cancel";
        };
    }

    private HttpHeaders headers(String idempotencyKey, String traceId, String requestId) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        if (idempotencyKey != null && !idempotencyKey.isBlank()) {
            headers.set("Idempotency-Key", idempotencyKey);
        }
        if (traceId != null && !traceId.isBlank()) {
            headers.set("x-trace-id", traceId);
        }
        if (requestId != null && !requestId.isBlank()) {
            headers.set("x-request-id", requestId);
        }
        return headers;
    }
}
