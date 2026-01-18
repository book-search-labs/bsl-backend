package com.bsl.search.opensearch;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
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
public class OpenSearchGateway {
    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;
    private final OpenSearchProperties properties;

    public OpenSearchGateway(
        @Qualifier("openSearchRestTemplate") RestTemplate restTemplate,
        ObjectMapper objectMapper,
        OpenSearchProperties properties
    ) {
        this.restTemplate = restTemplate;
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    public List<String> searchLexical(String query, int topK) {
        return searchLexical(query, topK, null, null);
    }

    public List<String> searchLexical(String query, int topK, Map<String, Double> boost, Integer timeBudgetMs) {
        return searchLexical(query, topK, boost, timeBudgetMs, null, null, null, null);
    }

    public List<String> searchLexical(
        String query,
        int topK,
        Map<String, Double> boost,
        Integer timeBudgetMs,
        String operator,
        String minimumShouldMatch,
        List<Map<String, Object>> filters,
        List<String> fieldsOverride
    ) {
        List<String> fields = buildFields(boost, fieldsOverride);

        Map<String, Object> multiMatch = new LinkedHashMap<>();
        multiMatch.put("query", query);
        multiMatch.put("fields", fields);
        if (operator != null && !operator.isBlank()) {
            multiMatch.put("operator", operator);
        }
        if (minimumShouldMatch != null && !minimumShouldMatch.isBlank()) {
            multiMatch.put("minimum_should_match", minimumShouldMatch);
        }

        Map<String, Object> boolQuery = new LinkedHashMap<>();
        boolQuery.put("must", List.of(Map.of("multi_match", multiMatch)));
        boolQuery.put("must_not", List.of(Map.of("term", Map.of("is_hidden", true))));
        if (filters != null && !filters.isEmpty()) {
            boolQuery.put("filter", filters);
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("size", topK);
        body.put("query", Map.of("bool", boolQuery));

        JsonNode response = postJson("/" + properties.getDocIndex() + "/_search", body, timeBudgetMs);
        return extractDocIds(response);
    }

    public List<String> searchVector(List<Double> vector, int topK) {
        return searchVector(vector, topK, null, null);
    }

    public List<String> searchVector(List<Double> vector, int topK, Integer timeBudgetMs) {
        return searchVector(vector, topK, timeBudgetMs, null);
    }

    public List<String> searchVector(
        List<Double> vector,
        int topK,
        Integer timeBudgetMs,
        List<Map<String, Object>> filters
    ) {
        Map<String, Object> embedding = new LinkedHashMap<>();
        embedding.put("vector", vector);
        embedding.put("k", topK);
        if (filters != null && !filters.isEmpty()) {
            embedding.put("filter", Map.of("bool", Map.of("filter", filters)));
        }

        Map<String, Object> knn = new LinkedHashMap<>();
        knn.put("embedding", embedding);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("size", topK);
        body.put("query", Map.of("knn", knn));

        JsonNode response = postJson("/" + properties.getVecIndex() + "/_search", body, timeBudgetMs);
        return extractDocIds(response);
    }

    public Map<String, JsonNode> mgetSources(List<String> docIds) {
        return mgetSources(docIds, null);
    }

    public Map<String, JsonNode> mgetSources(List<String> docIds, Integer timeBudgetMs) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("ids", docIds);

        JsonNode response = postJson("/" + properties.getDocIndex() + "/_mget", body, timeBudgetMs);
        Map<String, JsonNode> sources = new LinkedHashMap<>();
        for (JsonNode docNode : response.path("docs")) {
            if (!docNode.path("found").asBoolean(false)) {
                continue;
            }
            JsonNode source = docNode.path("_source");
            String docId = source.path("doc_id").asText(null);
            if (docId == null || docId.isEmpty()) {
                docId = docNode.path("_id").asText(null);
            }
            if (docId != null) {
                sources.put(docId, source);
            }
        }
        return sources;
    }

    public JsonNode getSourceById(String docId) {
        return getSourceById(docId, null);
    }

    public JsonNode getSourceById(String docId, Integer timeBudgetMs) {
        if (docId == null || docId.isBlank()) {
            return null;
        }
        JsonNode response = getJson("/" + properties.getDocIndex() + "/_doc/" + docId, timeBudgetMs);
        if (response == null) {
            return null;
        }
        if (response.has("found") && !response.path("found").asBoolean(false)) {
            return null;
        }
        JsonNode source = response.path("_source");
        if (source.isMissingNode() || source.isNull()) {
            return null;
        }
        return source;
    }

    private JsonNode postJson(String path, Object body, Integer timeBudgetMs) {
        String url = buildUrl(path);
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        try {
            String payload = objectMapper.writeValueAsString(body);
            HttpEntity<String> entity = new HttpEntity<>(payload, headers);
            RestTemplate client = restTemplateFor(timeBudgetMs);
            ResponseEntity<String> response = client.exchange(url, HttpMethod.POST, entity, String.class);
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

    private JsonNode getJson(String path, Integer timeBudgetMs) {
        String url = buildUrl(path);
        try {
            RestTemplate client = restTemplateFor(timeBudgetMs);
            ResponseEntity<String> response = client.exchange(url, HttpMethod.GET, HttpEntity.EMPTY, String.class);
            return objectMapper.readTree(response.getBody());
        } catch (ResourceAccessException e) {
            throw new OpenSearchUnavailableException("OpenSearch unreachable: " + url, e);
        } catch (HttpStatusCodeException e) {
            int status = e.getStatusCode().value();
            if (status == 404) {
                return null;
            }
            if (status == 502 || status == 503 || status == 504) {
                throw new OpenSearchUnavailableException("OpenSearch unavailable: " + status, e);
            }
            throw new OpenSearchRequestException("OpenSearch error: " + status, e);
        } catch (JsonProcessingException e) {
            throw new OpenSearchRequestException("Failed to parse OpenSearch response", e);
        }
    }

    private String buildUrl(String path) {
        String base = properties.getBaseUrl();
        if (base.endsWith("/")) {
            base = base.substring(0, base.length() - 1);
        }
        return base + path;
    }

    private List<String> extractDocIds(JsonNode response) {
        List<String> docIds = new ArrayList<>();
        for (JsonNode hit : response.path("hits").path("hits")) {
            String docId = hit.path("_source").path("doc_id").asText(null);
            if (docId == null || docId.isEmpty()) {
                docId = hit.path("_id").asText(null);
            }
            if (docId != null) {
                docIds.add(docId);
            }
        }
        return docIds;
    }

    private List<String> buildFields(Map<String, Double> boost, List<String> fieldsOverride) {
        List<String> baseFields = fieldsOverride == null || fieldsOverride.isEmpty()
            ? List.of(
                "title_ko",
                "title_en",
                "authors.name_ko",
                "series_name",
                "publisher_name"
            )
            : fieldsOverride;

        if (boost == null || boost.isEmpty()) {
            return baseFields;
        }

        List<String> fields = new ArrayList<>(baseFields.size());
        for (String field : baseFields) {
            Double weight = boost.get(field);
            if (weight != null && weight > 0) {
                fields.add(field + "^" + weight);
            } else {
                fields.add(field);
            }
        }
        return fields;
    }

    private RestTemplate restTemplateFor(Integer timeBudgetMs) {
        if (timeBudgetMs == null) {
            return restTemplate;
        }
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(timeBudgetMs);
        factory.setReadTimeout(timeBudgetMs);
        return new RestTemplate(factory);
    }
}
