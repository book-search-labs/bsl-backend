package com.bsl.search.query;

import com.bsl.search.query.dto.QueryEnhanceRequest;
import com.bsl.search.query.dto.QueryEnhanceResponse;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

@Component
public class QueryServiceGateway {
    private final RestTemplate restTemplate;
    private final QueryServiceProperties properties;

    public QueryServiceGateway(
        @Qualifier("queryServiceRestTemplate") RestTemplate restTemplate,
        QueryServiceProperties properties
    ) {
        this.restTemplate = restTemplate;
        this.properties = properties;
    }

    public QueryEnhanceResponse enhance(
        QueryEnhanceRequest request,
        Integer timeoutMs,
        String traceId,
        String requestId,
        String traceparent
    ) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.add("x-trace-id", traceId);
        headers.add("x-request-id", requestId);
        if (traceparent != null && !traceparent.isBlank()) {
            headers.add("traceparent", traceparent);
        }

        HttpEntity<QueryEnhanceRequest> entity = new HttpEntity<>(request, headers);

        try {
            RestTemplate client = restTemplateFor(timeoutMs);
            ResponseEntity<QueryEnhanceResponse> response = client.exchange(
                buildUrl("/query/enhance"),
                HttpMethod.POST,
                entity,
                QueryEnhanceResponse.class
            );
            return response.getBody();
        } catch (ResourceAccessException e) {
            throw new QueryServiceUnavailableException("Query service unavailable", e);
        } catch (HttpStatusCodeException e) {
            throw new QueryServiceUnavailableException("Query service error: " + e.getStatusCode(), e);
        }
    }

    private String buildUrl(String path) {
        String base = properties.getBaseUrl();
        if (base.endsWith("/")) {
            base = base.substring(0, base.length() - 1);
        }
        return base + path;
    }

    private RestTemplate restTemplateFor(Integer timeBudgetMs) {
        if (timeBudgetMs == null || timeBudgetMs <= 0) {
            return restTemplate;
        }
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(timeBudgetMs);
        factory.setReadTimeout(timeBudgetMs);
        return new RestTemplate(factory);
    }
}
