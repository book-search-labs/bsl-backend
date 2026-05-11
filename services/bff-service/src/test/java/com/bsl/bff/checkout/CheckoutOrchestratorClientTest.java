package com.bsl.bff.checkout;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.bff.common.RequestContext;
import com.bsl.bff.config.DownstreamProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

class CheckoutOrchestratorClientTest {
    @Test
    void forwardsTraceAndIdempotencyHeaders() {
        RestTemplate restTemplate = mock(RestTemplate.class);
        CheckoutOrchestratorClient client = new CheckoutOrchestratorClient(
            restTemplate,
            downstream("http://localhost:8091"),
            new ObjectMapper()
        );
        when(restTemplate.exchange(any(URI.class), eq(HttpMethod.POST), any(HttpEntity.class), eq(String.class)))
            .thenReturn(ResponseEntity.ok("{}"));

        client.exchange(
            HttpMethod.POST,
            "/internal/checkouts",
            "{}",
            new RequestContext("request-1", "trace-1", "traceparent-1", 1L),
            "checkout:1:CREATE_ORDER",
            "session-1"
        );

        ArgumentCaptor<URI> uriCaptor = ArgumentCaptor.forClass(URI.class);
        @SuppressWarnings("rawtypes")
        ArgumentCaptor<HttpEntity> entityCaptor = ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate).exchange(uriCaptor.capture(), eq(HttpMethod.POST), entityCaptor.capture(), eq(String.class));

        assertThat(uriCaptor.getValue().toString()).isEqualTo("http://localhost:8091/internal/checkouts");
        HttpHeaders headers = entityCaptor.getValue().getHeaders();
        assertThat(headers.getFirst("x-request-id")).isEqualTo("request-1");
        assertThat(headers.getFirst("x-trace-id")).isEqualTo("trace-1");
        assertThat(headers.getFirst("traceparent")).isEqualTo("traceparent-1");
        assertThat(headers.getFirst("Idempotency-Key")).isEqualTo("checkout:1:CREATE_ORDER");
        assertThat(headers.getFirst("x-session-id")).isEqualTo("session-1");
    }

    private DownstreamProperties downstream(String baseUrl) {
        DownstreamProperties properties = new DownstreamProperties();
        DownstreamProperties.ServiceProperties checkout = new DownstreamProperties.ServiceProperties();
        checkout.setBaseUrl(baseUrl);
        properties.setCheckoutOrchestratorService(checkout);
        return properties;
    }
}
