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
    private static final double WEIGHT_FACTOR = 0.02;
    private static final double CTR_FACTOR = 5.0;
    private static final double POPULARITY_FACTOR = 2.0;

    private final ObjectMapper objectMapper;
    private final OpenSearchProperties properties;
    private final RestTemplate restTemplate;

    public OpenSearchGateway(ObjectMapper objectMapper, OpenSearchProperties properties) {
        this.objectMapper = objectMapper;
        this.properties = properties;
        this.restTemplate = createRestTemplate(properties.getTimeoutMs());
    }

    public List<SuggestionHit> searchSuggestions(String query, int size) {
        return searchSuggestionsInternal(query, size, false);
    }

    public List<SuggestionHit> searchTrendingSuggestions(int size) {
        return searchTrendingSuggestionsInternal(size, false);
    }

    public List<SuggestionHit> searchAdminSuggestions(String query, int size, boolean includeBlocked) {
        return searchSuggestionsInternal(query, size, includeBlocked);
    }

    private List<SuggestionHit> searchSuggestionsInternal(String query, int size, boolean includeBlocked) {
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
        if (!includeBlocked) {
            boolQuery.put("must_not", List.of(Map.of("term", Map.of("is_blocked", true))));
        }

        Map<String, Object> functionScore = new LinkedHashMap<>();
        functionScore.put("query", Map.of("bool", boolQuery));
        functionScore.put("score_mode", "sum");
        functionScore.put("boost_mode", "sum");
        functionScore.put(
            "functions",
            List.of(
                Map.of("field_value_factor", Map.of("field", "weight", "factor", WEIGHT_FACTOR, "missing", 1)),
                Map.of("field_value_factor", Map.of("field", "ctr_7d", "factor", CTR_FACTOR, "missing", 0)),
                Map.of("field_value_factor", Map.of("field", "popularity_7d", "factor", POPULARITY_FACTOR, "missing", 0))
            )
        );

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("size", size);
        body.put("query", Map.of("function_score", functionScore));
        body.put("_source", List.of(
            "suggest_id",
            "type",
            "lang",
            "text",
            "value",
            "target_id",
            "target_doc_id",
            "weight",
            "ctr_7d",
            "popularity_7d",
            "is_blocked"
        ));

        JsonNode response = postJson("/" + properties.getIndex() + "/_search", body);
        return extractSuggestions(response);
    }

    private List<SuggestionHit> searchTrendingSuggestionsInternal(int size, boolean includeBlocked) {
        Map<String, Object> boolQuery = new LinkedHashMap<>();
        boolQuery.put("must", List.of(Map.of("match_all", Map.of())));
        if (!includeBlocked) {
            boolQuery.put("must_not", List.of(Map.of("term", Map.of("is_blocked", true))));
        }

        Map<String, Object> functionScore = new LinkedHashMap<>();
        functionScore.put("query", Map.of("bool", boolQuery));
        functionScore.put("score_mode", "sum");
        functionScore.put("boost_mode", "sum");
        functionScore.put(
            "functions",
            List.of(
                Map.of("field_value_factor", Map.of("field", "weight", "factor", WEIGHT_FACTOR, "missing", 1)),
                Map.of("field_value_factor", Map.of("field", "ctr_7d", "factor", CTR_FACTOR, "missing", 0)),
                Map.of("field_value_factor", Map.of("field", "popularity_7d", "factor", POPULARITY_FACTOR, "missing", 0))
            )
        );

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("size", size);
        body.put("query", Map.of("function_score", functionScore));
        body.put("sort", List.of(
            Map.of("_score", Map.of("order", "desc")),
            Map.of("popularity_7d", Map.of("order", "desc", "missing", "_last")),
            Map.of("ctr_7d", Map.of("order", "desc", "missing", "_last")),
            Map.of("weight", Map.of("order", "desc", "missing", "_last"))
        ));
        body.put("_source", List.of(
            "suggest_id",
            "type",
            "lang",
            "text",
            "value",
            "target_id",
            "target_doc_id",
            "weight",
            "ctr_7d",
            "popularity_7d",
            "is_blocked"
        ));

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
            hits.add(
                new SuggestionHit(
                    source.path("suggest_id").asText(null),
                    text,
                    source.path("type").asText(null),
                    source.path("lang").asText(null),
                    source.path("target_id").asText(null),
                    source.path("target_doc_id").asText(null),
                    source.path("weight").isNumber() ? source.path("weight").asInt() : null,
                    source.path("ctr_7d").isNumber() ? source.path("ctr_7d").asDouble() : null,
                    source.path("popularity_7d").isNumber() ? source.path("popularity_7d").asDouble() : null,
                    source.path("is_blocked").asBoolean(false),
                    score
                )
            );
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

    public SuggestionHit getSuggestion(String suggestId) {
        JsonNode response = getJson("/" + properties.getIndex() + "/_doc/" + suggestId);
        JsonNode source = response.path("_source");
        if (source.isMissingNode() || source.isNull()) {
            return null;
        }
        String text = source.path("text").asText(null);
        if (text == null || text.isBlank()) {
            text = source.path("value").asText(null);
        }
        if (text == null || text.isBlank()) {
            return null;
        }
        return new SuggestionHit(
            source.path("suggest_id").asText(null),
            text,
            source.path("type").asText(null),
            source.path("lang").asText(null),
            source.path("target_id").asText(null),
            source.path("target_doc_id").asText(null),
            source.path("weight").isNumber() ? source.path("weight").asInt() : null,
            source.path("ctr_7d").isNumber() ? source.path("ctr_7d").asDouble() : null,
            source.path("popularity_7d").isNumber() ? source.path("popularity_7d").asDouble() : null,
            source.path("is_blocked").asBoolean(false),
            0.0
        );
    }

    public void updateSuggestion(String suggestId, Map<String, Object> fields) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("doc", fields);
        postJson("/" + properties.getIndex() + "/_update/" + suggestId, body);
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

    private JsonNode getJson(String path) {
        String url = buildUrl(path);
        HttpHeaders headers = buildHeaders();
        try {
            HttpEntity<Void> entity = new HttpEntity<>(headers);
            ResponseEntity<String> response = restTemplate.exchange(url, HttpMethod.GET, entity, String.class);
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

    private RestTemplate createRestTemplate(int timeoutMs) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(timeoutMs);
        factory.setReadTimeout(timeoutMs);
        return new RestTemplate(factory);
    }

    public static class SuggestionHit {
        private final String suggestId;
        private final String text;
        private final String type;
        private final String lang;
        private final String targetId;
        private final String targetDocId;
        private final Integer weight;
        private final Double ctr7d;
        private final Double popularity7d;
        private final boolean blocked;
        private final double score;

        public SuggestionHit(
            String suggestId,
            String text,
            String type,
            String lang,
            String targetId,
            String targetDocId,
            Integer weight,
            Double ctr7d,
            Double popularity7d,
            boolean blocked,
            double score
        ) {
            this.suggestId = suggestId;
            this.text = text;
            this.type = type;
            this.lang = lang;
            this.targetId = targetId;
            this.targetDocId = targetDocId;
            this.weight = weight;
            this.ctr7d = ctr7d;
            this.popularity7d = popularity7d;
            this.blocked = blocked;
            this.score = score;
        }

        public String getSuggestId() {
            return suggestId;
        }

        public String getText() {
            return text;
        }

        public String getType() {
            return type;
        }

        public String getLang() {
            return lang;
        }

        public String getTargetId() {
            return targetId;
        }

        public String getTargetDocId() {
            return targetDocId;
        }

        public Integer getWeight() {
            return weight;
        }

        public Double getCtr7d() {
            return ctr7d;
        }

        public Double getPopularity7d() {
            return popularity7d;
        }

        public boolean isBlocked() {
            return blocked;
        }

        public double getScore() {
            return score;
        }
    }
}
