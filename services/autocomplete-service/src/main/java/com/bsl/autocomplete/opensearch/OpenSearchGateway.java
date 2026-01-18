package com.bsl.autocomplete.opensearch;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
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
public class OpenSearchGateway {
    private static final int MAX_EXPANSIONS = 50;

    private final ObjectMapper objectMapper;
    private final OpenSearchProperties properties;
    private final RestTemplate restTemplate;

    public OpenSearchGateway(ObjectMapper objectMapper, OpenSearchProperties properties) {
        this.objectMapper = objectMapper;
        this.properties = properties;
        this.restTemplate = createRestTemplate(properties.getTimeoutMs());
    }

    public List<SuggestionHit> searchSuggestions(String query, int size) {
        Map<String, Object> phrasePrefix = new LinkedHashMap<>();
        phrasePrefix.put("query", query);
        phrasePrefix.put("max_expansions", MAX_EXPANSIONS);

        Map<String, Object> matchPhrasePrefix = Map.of("text", phrasePrefix);

        Map<String, Object> matchQuery = new LinkedHashMap<>();
        matchQuery.put("query", query);
        matchQuery.put("operator", "and");

        Map<String, Object> fallbackMatch = Map.of("text", matchQuery);

        List<Map<String, Object>> shouldQueries = List.of(
            Map.of("match_phrase_prefix", matchPhrasePrefix),
            Map.of("match", fallbackMatch)
        );

        Map<String, Object> boolQuery = new LinkedHashMap<>();
        boolQuery.put("should", shouldQueries);
        boolQuery.put("minimum_should_match", 1);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("size", size);
        body.put("query", Map.of("bool", boolQuery));
        body.put("_source", List.of("text", "value"));

        JsonNode response = postJson("/" + properties.getIndex() + "/_search", body);
        return extractSuggestions(response);
    }

    private List<SuggestionHit> extractSuggestions(JsonNode response) {
        List<SuggestionHit> hits = new ArrayList<>();
        for (JsonNode hit : response.path("hits").path("hits")) {
            JsonNode source = hit.path("_source");
            if (source.isMissingNode() || source.isNull()) {
                continue;
            }
            String text = source.path("text").asText(null);
            if (text == null || text.isBlank()) {
                text = source.path("value").asText(null);
            }
            if (text == null || text.isBlank()) {
                continue;
            }
            double score = hit.path("_score").asDouble(0.0);
            hits.add(new SuggestionHit(text, score));
        }
        return hits;
    }

    private JsonNode postJson(String path, Object body) {
        String url = buildUrl(path);
        HttpHeaders headers = buildHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        try {
            String payload = objectMapper.writeValueAsString(body);
            HttpEntity<String> entity = new HttpEntity<>(payload, headers);
            ResponseEntity<String> response = restTemplate.exchange(url, HttpMethod.POST, entity, String.class);
            return objectMapper.readTree(response.getBody());
        } catch (ResourceAccessException e) {
            throw new OpenSearchUnavailableException("OpenSearch unreachable: " + url, e);
        } catch (HttpStatusCodeException e) {
            int status = e.getStatusCode().value();
            if (status == 502 || status == 503 || status == 504) {
                throw new OpenSearchUnavailableException("OpenSearch unavailable: " + status, e);
            }
            throw new OpenSearchRequestException("OpenSearch error: " + status, e);
        } catch (JsonProcessingException e) {
            throw new OpenSearchRequestException("Failed to parse OpenSearch response", e);
        }
    }

    private String buildUrl(String path) {
        String base = properties.getUrl();
        if (base.endsWith("/")) {
            base = base.substring(0, base.length() - 1);
        }
        return base + path;
    }

    private HttpHeaders buildHeaders() {
        HttpHeaders headers = new HttpHeaders();
        String username = properties.getUsername();
        String password = properties.getPassword();
        if (username != null && !username.isBlank() && password != null && !password.isBlank()) {
            String auth = username + ":" + password;
            String encoded = Base64.getEncoder().encodeToString(auth.getBytes(StandardCharsets.UTF_8));
            headers.set(HttpHeaders.AUTHORIZATION, "Basic " + encoded);
        }
        return headers;
    }

    private RestTemplate createRestTemplate(int timeoutMs) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(timeoutMs);
        factory.setReadTimeout(timeoutMs);
        return new RestTemplate(factory);
    }

    public static class SuggestionHit {
        private final String text;
        private final double score;

        public SuggestionHit(String text, double score) {
            this.text = text;
            this.score = score;
        }

        public String getText() {
            return text;
        }

        public double getScore() {
            return score;
        }
    }
}
