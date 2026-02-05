package com.bsl.bff.client;

import com.bsl.bff.common.DownstreamHeaders;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.config.DownstreamProperties;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
public class ReadyCheckService {
    private final RestTemplate queryRestTemplate;
    private final RestTemplate searchRestTemplate;
    private final RestTemplate autocompleteRestTemplate;
    private final DownstreamProperties properties;

    public ReadyCheckService(
        RestTemplate queryServiceRestTemplate,
        RestTemplate searchServiceRestTemplate,
        RestTemplate autocompleteServiceRestTemplate,
        DownstreamProperties properties
    ) {
        this.queryRestTemplate = queryServiceRestTemplate;
        this.searchRestTemplate = searchServiceRestTemplate;
        this.autocompleteRestTemplate = autocompleteServiceRestTemplate;
        this.properties = properties;
    }

    public Map<String, String> check(RequestContext context) {
        Map<String, String> downstream = new LinkedHashMap<>();
        downstream.put("query_service", probe(queryRestTemplate, properties.getQueryService().getBaseUrl(), context));
        downstream.put("search_service", probe(searchRestTemplate, properties.getSearchService().getBaseUrl(), context));
        downstream.put("autocomplete_service", probe(autocompleteRestTemplate, properties.getAutocompleteService().getBaseUrl(), context));
        return downstream;
    }

    private String probe(RestTemplate restTemplate, String baseUrl, RequestContext context) {
        String url = baseUrl + "/health";
        HttpHeaders headers = DownstreamHeaders.from(context);
        HttpEntity<Void> entity = new HttpEntity<>(headers);
        try {
            ResponseEntity<String> response = restTemplate.exchange(url, HttpMethod.GET, entity, String.class);
            return response.getStatusCode() == HttpStatus.OK ? "ok" : "error";
        } catch (Exception ex) {
            return "error";
        }
    }
}
