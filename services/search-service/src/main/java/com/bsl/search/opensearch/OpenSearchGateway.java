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
        List<String> fields = List.of(
            "title_ko",
            "title_en",
            "authors.name_ko",
            "publisher_name"
        );

        Map<String, Object> multiMatch = new LinkedHashMap<>();
        multiMatch.put("query", query);
        multiMatch.put("fields", fields);

        Map<String, Object> boolQuery = new LinkedHashMap<>();
        boolQuery.put("must", List.of(Map.of("multi_match", multiMatch)));
        boolQuery.put("must_not", List.of(Map.of("term", Map.of("is_hidden", true))));

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("size", topK);
        body.put("query", Map.of("bool", boolQuery));

        JsonNode response = postJson("/" + properties.getDocIndex() + "/_search", body);
        return extractDocIds(response);
    }

    public List<String> searchVector(List<Double> vector, int topK) {
        Map<String, Object> embedding = new LinkedHashMap<>();
        embedding.put("vector", vector);
        embedding.put("k", topK);

        Map<String, Object> knn = new LinkedHashMap<>();
        knn.put("embedding", embedding);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("size", topK);
        body.put("query", Map.of("knn", knn));

        JsonNode response = postJson("/" + properties.getVecIndex() + "/_search", body);
        return extractDocIds(response);
    }

    public Map<String, JsonNode> mgetSources(List<String> docIds) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("ids", docIds);

        JsonNode response = postJson("/" + properties.getDocIndex() + "/_mget", body);
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

    private JsonNode postJson(String path, Object body) {
        String url = buildUrl(path);
        HttpHeaders headers = new HttpHeaders();
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
}
