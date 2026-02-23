package com.bsl.bff.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.config.DownstreamProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestTemplate;

class CommerceServiceClientTest {
    @Test
    void preservesEncodedMaterialIdWhenForwarding() {
        RestTemplate restTemplate = mock(RestTemplate.class);
        CommerceServiceClient client = new CommerceServiceClient(
            restTemplate,
            downstream("http://localhost:8091"),
            new ObjectMapper()
        );
        when(restTemplate.exchange(any(URI.class), eq(HttpMethod.GET), any(HttpEntity.class), eq(String.class)))
            .thenReturn(ResponseEntity.ok("{}"));

        client.exchange(
            HttpMethod.GET,
            "/api/v1/materials/nlk%3ACDM000000001/current-offer",
            null,
            null
        );

        ArgumentCaptor<URI> uriCaptor = ArgumentCaptor.forClass(URI.class);
        verify(restTemplate).exchange(uriCaptor.capture(), eq(HttpMethod.GET), any(HttpEntity.class), eq(String.class));
        assertThat(uriCaptor.getValue().toString())
            .isEqualTo("http://localhost:8091/api/v1/materials/nlk%3ACDM000000001/current-offer");
    }

    @Test
    void normalizesTrailingSlashAndKeepsQuery() {
        RestTemplate restTemplate = mock(RestTemplate.class);
        CommerceServiceClient client = new CommerceServiceClient(
            restTemplate,
            downstream("http://localhost:8091/"),
            new ObjectMapper()
        );
        when(restTemplate.exchange(any(URI.class), eq(HttpMethod.GET), any(HttpEntity.class), eq(String.class)))
            .thenReturn(ResponseEntity.ok("{}"));

        client.exchange(
            HttpMethod.GET,
            "/api/v1/skus?materialId=nlk%3ACDM000000001",
            null,
            null
        );

        ArgumentCaptor<URI> uriCaptor = ArgumentCaptor.forClass(URI.class);
        verify(restTemplate).exchange(uriCaptor.capture(), eq(HttpMethod.GET), any(HttpEntity.class), eq(String.class));
        assertThat(uriCaptor.getValue().toString())
            .isEqualTo("http://localhost:8091/api/v1/skus?materialId=nlk%3ACDM000000001");
    }

    @Test
    void parsesJsonDownstreamError() {
        RestTemplate restTemplate = mock(RestTemplate.class);
        CommerceServiceClient client = new CommerceServiceClient(
            restTemplate,
            downstream("http://localhost:8091"),
            new ObjectMapper()
        );
        HttpClientErrorException exception = HttpClientErrorException.create(
            HttpStatus.CONFLICT,
            "Conflict",
            HttpHeaders.EMPTY,
            "{\"error\":{\"code\":\"price_changed\",\"message\":\"가격이 변경되었습니다.\"}}".getBytes(StandardCharsets.UTF_8),
            StandardCharsets.UTF_8
        );
        when(restTemplate.exchange(any(URI.class), eq(HttpMethod.POST), any(HttpEntity.class), eq(String.class)))
            .thenThrow(exception);

        assertThatThrownBy(() -> client.exchange(HttpMethod.POST, "/api/v1/orders", "{}", null))
            .isInstanceOf(DownstreamException.class)
            .satisfies((error) -> {
                DownstreamException downstreamException = (DownstreamException) error;
                assertThat(downstreamException.getStatus()).isEqualTo(HttpStatus.CONFLICT);
                assertThat(downstreamException.getCode()).isEqualTo("price_changed");
                assertThat(downstreamException.getMessage()).isEqualTo("가격이 변경되었습니다.");
            });
    }

    @Test
    void usesTextBodyAsMessageWhenJsonParseFails() {
        RestTemplate restTemplate = mock(RestTemplate.class);
        CommerceServiceClient client = new CommerceServiceClient(
            restTemplate,
            downstream("http://localhost:8091"),
            new ObjectMapper()
        );
        HttpClientErrorException exception = HttpClientErrorException.create(
            HttpStatus.BAD_REQUEST,
            "Bad Request",
            HttpHeaders.EMPTY,
            "cart is empty".getBytes(StandardCharsets.UTF_8),
            StandardCharsets.UTF_8
        );
        when(restTemplate.exchange(any(URI.class), eq(HttpMethod.POST), any(HttpEntity.class), eq(String.class)))
            .thenThrow(exception);

        assertThatThrownBy(() -> client.exchange(HttpMethod.POST, "/api/v1/orders", "{}", null))
            .isInstanceOf(DownstreamException.class)
            .satisfies((error) -> {
                DownstreamException downstreamException = (DownstreamException) error;
                assertThat(downstreamException.getStatus()).isEqualTo(HttpStatus.BAD_REQUEST);
                assertThat(downstreamException.getCode()).isEqualTo("commerce_service_bad_request");
                assertThat(downstreamException.getMessage()).isEqualTo("cart is empty");
            });
    }

    private DownstreamProperties downstream(String commerceBaseUrl) {
        DownstreamProperties properties = new DownstreamProperties();
        DownstreamProperties.ServiceProperties commerce = new DownstreamProperties.ServiceProperties();
        commerce.setBaseUrl(commerceBaseUrl);
        properties.setCommerceService(commerce);
        return properties;
    }
}
