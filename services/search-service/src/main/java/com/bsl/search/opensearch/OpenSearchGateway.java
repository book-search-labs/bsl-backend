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
    private static final Map<String, Double> DEFAULT_PRIMARY_FIELD_BOOST = Map.ofEntries(
        Map.entry("title_ko", 8.0d),
        Map.entry("title_en", 7.0d),
        Map.entry("series_name", 4.0d),
        Map.entry("author_names_ko", 3.0d),
        Map.entry("author_names_en", 2.5d),
        Map.entry("publisher_name", 2.0d)
    );

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
        OpenSearchQueryResult result = searchLexicalDetailed(
            query,
            topK,
            boost,
            timeBudgetMs,
            operator,
            minimumShouldMatch,
            filters,
            fieldsOverride,
            false
        );
        return result == null ? List.of() : result.getDocIds();
    }

    public OpenSearchQueryResult searchLexicalDetailed(
        String query,
        int topK,
        Map<String, Double> boost,
        Integer timeBudgetMs,
        String operator,
        String minimumShouldMatch,
        List<Map<String, Object>> filters,
        List<String> fieldsOverride,
        boolean explain
    ) {
        String trimmed = trimToNull(query);
        List<String> fields = buildPrimaryFields(boost, fieldsOverride);
        List<Map<String, Object>> shouldQueries = new ArrayList<>();
        shouldQueries.add(Map.of("multi_match", buildPrimaryMultiMatch(query, fields, operator, minimumShouldMatch)));
        if (trimmed != null) {
            shouldQueries.add(buildPhraseBoostClause(trimmed));
        }
        shouldQueries.add(Map.of("multi_match", buildCompactMultiMatch(query)));
        shouldQueries.add(Map.of("multi_match", buildAutoPrefixMultiMatch(query)));

        Map<String, Object> boolQuery = new LinkedHashMap<>();
        boolQuery.put("should", shouldQueries);
        boolQuery.put("minimum_should_match", 1);
        boolQuery.put("filter", buildBooleanFilterClauses(filters, true));

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("size", topK);
        body.put("track_total_hits", false);
        body.put("query", Map.of("bool", boolQuery));
        if (explain) {
            body.put("explain", true);
        }

        JsonNode response = postJson("/" + properties.getDocIndex() + "/_search", body, timeBudgetMs);
        return new OpenSearchQueryResult(extractDocIds(response), body, extractScoresByDocId(response));
    }

    private Map<String, Object> buildPrimaryMultiMatch(
        String query,
        List<String> fields,
        String operator,
        String minimumShouldMatch
    ) {
        Map<String, Object> multiMatch = new LinkedHashMap<>();
        multiMatch.put("query", query);
        multiMatch.put("fields", fields);
        multiMatch.put("lenient", true);
        if (operator != null && !operator.isBlank()) {
            multiMatch.put("operator", operator);
        }
        if (minimumShouldMatch != null && !minimumShouldMatch.isBlank()) {
            multiMatch.put("minimum_should_match", minimumShouldMatch);
        }
        multiMatch.put("type", "best_fields");
        return multiMatch;
    }

    private Map<String, Object> buildPhraseBoostClause(String trimmedQuery) {
        return Map.of(
            "dis_max",
            Map.of(
                "tie_breaker",
                0.2d,
                "queries",
                List.of(
                    Map.of("match_phrase", Map.of("title_ko", Map.of("query", trimmedQuery, "slop", 1, "boost", 15.0d))),
                    Map.of("match_phrase", Map.of("title_en", Map.of("query", trimmedQuery, "slop", 1, "boost", 12.0d))),
                    Map.of("match_phrase", Map.of("series_name", Map.of("query", trimmedQuery, "slop", 1, "boost", 6.0d)))
                )
            )
        );
    }

    private Map<String, Object> buildCompactMultiMatch(String query) {
        Map<String, Object> multiMatch = new LinkedHashMap<>();
        multiMatch.put("query", query);
        multiMatch.put(
            "fields",
            List.of(
                "title_ko.compact^6",
                "title_en.compact^5",
                "series_name.compact^3",
                "author_names_ko.compact^2.5",
                "author_names_en.compact^2.0",
                "publisher_name.compact^2"
            )
        );
        multiMatch.put("type", "best_fields");
        multiMatch.put("operator", "or");
        multiMatch.put("lenient", true);
        return multiMatch;
    }

    private Map<String, Object> buildAutoPrefixMultiMatch(String query) {
        Map<String, Object> multiMatch = new LinkedHashMap<>();
        multiMatch.put("query", query);
        multiMatch.put("type", "bool_prefix");
        multiMatch.put(
            "fields",
            List.of(
                "title_ko.auto^4",
                "title_en.auto^3.5",
                "series_name.auto^2.8",
                "author_names_ko.auto^2.2",
                "author_names_en.auto^1.8",
                "publisher_name.auto^1.8"
            )
        );
        multiMatch.put("lenient", true);
        return multiMatch;
    }

    private String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }

    public OpenSearchQueryResult searchLexicalByDslDetailed(
        Map<String, Object> queryDsl,
        int topK,
        Integer timeBudgetMs,
        List<Map<String, Object>> filters,
        boolean explain
    ) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("size", topK);
        body.put("track_total_hits", false);
        body.put("query", applyGlobalConstraints(queryDsl, filters));
        if (explain) {
            body.put("explain", true);
        }

        JsonNode response = postJson("/" + properties.getDocIndex() + "/_search", body, timeBudgetMs);
        return new OpenSearchQueryResult(extractDocIds(response), body, extractScoresByDocId(response));
    }

    public OpenSearchQueryResult searchMatchAllDetailed(
        int topK,
        Integer timeBudgetMs,
        List<Map<String, Object>> filters,
        boolean explain
    ) {
        Map<String, Object> boolQuery = new LinkedHashMap<>();
        boolQuery.put("must", List.of(Map.of("match_all", Map.of())));
        boolQuery.put("filter", buildBooleanFilterClauses(filters, true));

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("size", topK);
        body.put("track_total_hits", false);
        body.put("query", Map.of("bool", boolQuery));
        if (explain) {
            body.put("explain", true);
        }

        JsonNode response = postJson("/" + properties.getDocIndex() + "/_search", body, timeBudgetMs);
        return new OpenSearchQueryResult(extractDocIds(response), body, extractScoresByDocId(response));
    }

    private Map<String, Object> applyGlobalConstraints(
        Map<String, Object> queryDsl,
        List<Map<String, Object>> filters
    ) {
        if (queryDsl == null || queryDsl.isEmpty()) {
            return Map.of(
                "bool",
                Map.of(
                    "must", List.of(Map.of("match_all", Map.of())),
                    "filter", buildBooleanFilterClauses(filters, true)
                )
            );
        }

        if (queryDsl.containsKey("bool") && queryDsl.get("bool") instanceof Map<?, ?> boolRaw) {
            Map<String, Object> boolQuery = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : boolRaw.entrySet()) {
                if (entry.getKey() instanceof String key) {
                    boolQuery.put(key, entry.getValue());
                }
            }

            List<Object> filterClauses = toClauseList(boolQuery.get("filter"));
            filterClauses.addAll(buildBooleanFilterClauses(filters, true));
            boolQuery.put("filter", filterClauses);
            return Map.of("bool", boolQuery);
        }

        Map<String, Object> boolQuery = new LinkedHashMap<>();
        boolQuery.put("must", List.of(queryDsl));
        boolQuery.put("filter", buildBooleanFilterClauses(filters, true));
        return Map.of("bool", boolQuery);
    }

    private List<Object> buildBooleanFilterClauses(List<Map<String, Object>> filters, boolean includeVisibilityFilter) {
        List<Object> filterClauses = new ArrayList<>();
        if (includeVisibilityFilter) {
            filterClauses.add(Map.of("term", Map.of("is_hidden", false)));
        }
        if (filters != null && !filters.isEmpty()) {
            filterClauses.addAll(filters);
        }
        return filterClauses;
    }

    private List<Object> toClauseList(Object value) {
        if (value instanceof List<?> list) {
            return new ArrayList<>(list);
        }
        if (value == null) {
            return new ArrayList<>();
        }
        List<Object> wrapped = new ArrayList<>();
        wrapped.add(value);
        return wrapped;
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
        OpenSearchQueryResult result = searchVectorDetailed(vector, topK, timeBudgetMs, filters, false);
        return result == null ? List.of() : result.getDocIds();
    }

    public OpenSearchQueryResult searchVectorDetailed(
        List<Double> vector,
        int topK,
        Integer timeBudgetMs,
        List<Map<String, Object>> filters,
        boolean explain
    ) {
        return searchVectorDetailedOnIndex(vector, topK, properties.getVecIndex(), timeBudgetMs, filters, explain, true);
    }

    public OpenSearchQueryResult searchChunkVectorDetailed(
        List<Double> vector,
        int topK,
        Integer timeBudgetMs,
        List<Map<String, Object>> filters,
        boolean explain
    ) {
        String indexName = properties.getChunkIndex();
        if (indexName == null || indexName.isBlank()) {
            throw new OpenSearchRequestException("chunk index is not configured", null);
        }
        return searchVectorDetailedOnIndex(vector, topK, indexName, timeBudgetMs, filters, explain, false);
    }

    private OpenSearchQueryResult searchVectorDetailedOnIndex(
        List<Double> vector,
        int topK,
        String indexName,
        Integer timeBudgetMs,
        List<Map<String, Object>> filters,
        boolean explain,
        boolean includeVisibilityFilter
    ) {
        Map<String, Object> embedding = new LinkedHashMap<>();
        embedding.put("vector", vector);
        embedding.put("k", topK);
        List<Object> filterClauses = buildBooleanFilterClauses(filters, includeVisibilityFilter);
        if (!filterClauses.isEmpty()) {
            embedding.put("filter", Map.of("bool", Map.of("filter", filterClauses)));
        }

        Map<String, Object> knn = new LinkedHashMap<>();
        knn.put("embedding", embedding);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("size", topK);
        body.put("track_total_hits", false);
        body.put("_source", List.of("doc_id"));
        body.put("query", Map.of("knn", knn));
        if (explain) {
            body.put("explain", true);
        }

        JsonNode response = postJson("/" + indexName + "/_search", body, timeBudgetMs);
        return new OpenSearchQueryResult(extractDocIds(response), body, extractScoresByDocId(response));
    }

    public OpenSearchQueryResult searchVectorByTextDetailed(
        String queryText,
        int topK,
        String modelId,
        Integer timeBudgetMs,
        List<Map<String, Object>> filters,
        boolean explain
    ) {
        Map<String, Object> neural = new LinkedHashMap<>();
        Map<String, Object> embedding = new LinkedHashMap<>();
        embedding.put("query_text", queryText);
        embedding.put("model_id", modelId);
        embedding.put("k", topK);
        List<Object> filterClauses = buildBooleanFilterClauses(filters, true);
        if (!filterClauses.isEmpty()) {
            embedding.put("filter", Map.of("bool", Map.of("filter", filterClauses)));
        }
        neural.put("embedding", embedding);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("size", topK);
        body.put("track_total_hits", false);
        body.put("_source", List.of("doc_id"));
        body.put("query", Map.of("neural", neural));
        if (explain) {
            body.put("explain", true);
        }

        JsonNode response = postJson("/" + properties.getVecIndex() + "/_search", body, timeBudgetMs);
        return new OpenSearchQueryResult(extractDocIds(response), body, extractScoresByDocId(response));
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

    private Map<String, Double> extractScoresByDocId(JsonNode response) {
        Map<String, Double> scores = new LinkedHashMap<>();
        for (JsonNode hit : response.path("hits").path("hits")) {
            String docId = hit.path("_source").path("doc_id").asText(null);
            if (docId == null || docId.isEmpty()) {
                docId = hit.path("_id").asText(null);
            }
            if (docId == null || docId.isBlank()) {
                continue;
            }
            JsonNode scoreNode = hit.get("_score");
            if (scoreNode != null && scoreNode.isNumber()) {
                scores.put(docId, scoreNode.asDouble());
            }
        }
        return scores;
    }

    private List<String> buildPrimaryFields(Map<String, Double> boost, List<String> fieldsOverride) {
        List<String> baseFields = fieldsOverride == null || fieldsOverride.isEmpty()
            ? List.of(
                "title_ko",
                "title_en",
                "series_name",
                "author_names_ko",
                "author_names_en",
                "publisher_name"
            )
            : fieldsOverride;

        List<String> fields = new ArrayList<>(baseFields.size());
        for (String field : baseFields) {
            if (field == null) {
                continue;
            }
            String normalized = field.trim();
            if (normalized.isEmpty()) {
                continue;
            }
            if (normalized.contains("^")) {
                fields.add(normalized);
                continue;
            }
            Double weighted = null;
            if (boost != null && !boost.isEmpty()) {
                weighted = boost.get(normalized);
            }
            if (weighted == null) {
                weighted = DEFAULT_PRIMARY_FIELD_BOOST.get(normalized);
            }
            if (weighted != null && weighted > 0) {
                fields.add(normalized + "^" + weighted);
            } else {
                fields.add(normalized);
            }
        }

        if (!fields.isEmpty()) {
            return fields;
        }

        return List.of(
            "title_ko^8.0",
            "title_en^7.0",
            "series_name^4.0",
            "author_names_ko^3.0",
            "author_names_en^2.5",
            "publisher_name^2.0"
        );
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
