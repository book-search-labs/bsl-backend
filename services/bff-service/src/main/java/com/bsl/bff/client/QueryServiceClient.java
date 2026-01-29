package com.bsl.bff.client;

import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.common.DownstreamHeaders;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.config.DownstreamProperties;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.HashMap;
import java.util.Map;
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
public class QueryServiceClient {
    private final RestTemplate restTemplate;
    private final DownstreamProperties.ServiceProperties properties;

    public QueryServiceClient(RestTemplate queryServiceRestTemplate, DownstreamProperties downstreamProperties) {
        this.restTemplate = queryServiceRestTemplate;
        this.properties = downstreamProperties.getQueryService();
    }

    public JsonNode fetchQueryContext(String rawQuery, RequestContext context) {
        String url = properties.getBaseUrl() + "/query-context";
        Map<String, Object> query = new HashMap<>();
        query.put("raw", rawQuery);
        Map<String, Object> body = new HashMap<>();
        body.put("query", query);

        HttpHeaders headers = DownstreamHeaders.from(context);
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
}
