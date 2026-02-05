package com.bsl.bff.client;

import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.common.DownstreamHeaders;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.config.DownstreamProperties;
import com.bsl.bff.security.AuthContext;
import com.bsl.bff.security.AuthContextHolder;
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

    public CommerceServiceClient(RestTemplate commerceServiceRestTemplate, DownstreamProperties downstreamProperties) {
        this.restTemplate = commerceServiceRestTemplate;
        this.properties = downstreamProperties.getCommerceService();
    }

    public ResponseEntity<String> exchange(HttpMethod method, String pathWithQuery, String body, RequestContext context) {
        String url = properties.getBaseUrl() + pathWithQuery;
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
            return restTemplate.exchange(url, method, entity, String.class);
        } catch (ResourceAccessException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "commerce_service_timeout",
                "Commerce service timeout");
        } catch (HttpStatusCodeException ex) {
            HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
            if (status == null) {
                status = HttpStatus.SERVICE_UNAVAILABLE;
            }
            String code = status.is4xxClientError() ? "commerce_service_bad_request" : "commerce_service_error";
            throw new DownstreamException(status, code, "Commerce service error");
        }
    }
}
