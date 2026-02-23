package com.bsl.search;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bsl.search.opensearch.OpenSearchGateway;
import com.bsl.search.opensearch.OpenSearchQueryResult;
import com.bsl.search.opensearch.OpenSearchUnavailableException;
import com.bsl.search.query.QueryServiceGateway;
import com.bsl.search.query.dto.QueryEnhanceResponse;
import com.bsl.search.ranking.RankingGateway;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SearchControllerQcV11Test {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private OpenSearchGateway openSearchGateway;

    @MockBean
    private RankingGateway rankingGateway;

    @MockBean
    private QueryServiceGateway queryServiceGateway;

    @Test
    void acceptsQcV11AndPropagatesIds() throws Exception {
        when(openSearchGateway.searchLexicalDetailed(eq("harry"), anyInt(), any(), any(), any(), any(), any(), any(), anyBoolean()))
            .thenReturn(new OpenSearchQueryResult(List.of("b1"), Map.of(), Map.of()));
        when(openSearchGateway.mgetSources(anyList(), any())).thenReturn(buildSources());

        Map<String, Object> payload = qcV11Payload(
            Map.of("raw", "harry", "norm", "harry", "final", "harry"),
            Map.of(
                "queryTextSource", "query.final",
                "lexical", Map.of("enabled", true, "topKHint", 50),
                "vector", Map.of("enabled", false),
                "rerank", Map.of("enabled", false)
            )
        );

        mockMvc.perform(post("/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(payload)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.trace_id").value("trace_demo"))
            .andExpect(jsonPath("$.request_id").value("req_demo"));
    }

    @Test
    void rejectsMissingChosenQueryText() throws Exception {
        Map<String, Object> payload = qcV11Payload(
            Map.of("raw", "harry", "norm", "harry"),
            Map.of("queryTextSource", "query.final", "lexical", Map.of("enabled", true), "vector", Map.of("enabled", false))
        );

        mockMvc.perform(post("/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(payload)))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error.code").value("bad_request"));
    }

    @Test
    void mapsVolumeFilterIntoLexicalQuery() throws Exception {
        when(openSearchGateway.searchLexicalDetailed(eq("harry"), anyInt(), any(), any(), any(), any(), any(), any(), anyBoolean()))
            .thenReturn(new OpenSearchQueryResult(List.of("b1"), Map.of(), Map.of()));
        when(openSearchGateway.mgetSources(anyList(), any())).thenReturn(buildSources());

        Map<String, Object> payload = qcV11Payload(
            Map.of("raw", "harry", "norm", "harry", "final", "harry"),
            Map.of(
                "queryTextSource", "query.final",
                "lexical", Map.of("enabled", true, "topKHint", 50),
                "vector", Map.of("enabled", false),
                "filters", List.of(
                    Map.of(
                        "and", List.of(
                            Map.of("scope", "CATALOG", "logicalField", "volume", "op", "eq", "value", 1)
                        )
                    )
                )
            )
        );

        mockMvc.perform(post("/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(payload)))
            .andExpect(status().isOk());

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<Map<String, Object>>> filtersCaptor = ArgumentCaptor.forClass(List.class);
        verify(openSearchGateway).searchLexicalDetailed(
            eq("harry"),
            anyInt(),
            any(),
            any(),
            any(),
            any(),
            filtersCaptor.capture(),
            any(),
            anyBoolean()
        );
        boolean hasVolume = filtersCaptor.getValue().stream()
            .anyMatch(entry -> entry.containsKey("term") && ((Map<String, Object>) entry.get("term")).containsKey("volume"));
        org.junit.jupiter.api.Assertions.assertTrue(hasVolume);
    }

    @Test
    void allowsQuerylessSearchWithFilters() throws Exception {
        when(openSearchGateway.searchMatchAllDetailed(anyInt(), any(), any(), anyBoolean()))
            .thenReturn(new com.bsl.search.opensearch.OpenSearchQueryResult(List.of("b1"), Map.of(), Map.of()));
        when(openSearchGateway.mgetSources(anyList(), any())).thenReturn(buildSources());

        Map<String, Object> payload = qcV11Payload(
            Map.of("raw", "", "norm", "", "final", ""),
            Map.of(
                "queryTextSource", "query.final",
                "lexical", Map.of("enabled", true),
                "vector", Map.of("enabled", false),
                "filters", List.of(
                    Map.of(
                        "and", List.of(
                            Map.of("scope", "CATALOG", "logicalField", "kdc_node_id", "op", "eq", "value", List.of(1, 2))
                        )
                    )
                )
            )
        );

        mockMvc.perform(post("/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(payload)))
            .andExpect(status().isOk());

        verify(openSearchGateway).searchMatchAllDetailed(anyInt(), any(), any(), anyBoolean());
    }

    @Test
    void prioritizesKoreanTitlesForCategoryBrowse() throws Exception {
        when(openSearchGateway.searchMatchAllDetailed(anyInt(), any(), any(), anyBoolean()))
            .thenReturn(new OpenSearchQueryResult(List.of("hanja", "korean"), Map.of(), Map.of()));
        when(openSearchGateway.mgetSources(anyList(), any())).thenReturn(buildSourcesForCategoryOrdering());

        Map<String, Object> payload = qcV11Payload(
            Map.of("raw", "", "norm", "", "final", ""),
            Map.of(
                "queryTextSource", "query.final",
                "lexical", Map.of("enabled", true),
                "vector", Map.of("enabled", false),
                "filters", List.of(
                    Map.of(
                        "and", List.of(
                            Map.of(
                                "scope",
                                "CATALOG",
                                "logicalField",
                                "kdc_path_codes",
                                "op",
                                "eq",
                                "value",
                                List.of("200", "210")
                            )
                        )
                    )
                )
            )
        );

        mockMvc.perform(post("/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(payload)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.hits[0].doc_id").value("korean"))
            .andExpect(jsonPath("$.hits[1].doc_id").value("hanja"));
    }

    @Test
    void mapsKdcNodeFilterIntoLexicalQuery() throws Exception {
        when(openSearchGateway.searchLexicalDetailed(eq("harry"), anyInt(), any(), any(), any(), any(), any(), any(), anyBoolean()))
            .thenReturn(new OpenSearchQueryResult(List.of("b1"), Map.of(), Map.of()));
        when(openSearchGateway.mgetSources(anyList(), any())).thenReturn(buildSources());

        Map<String, Object> payload = qcV11Payload(
            Map.of("raw", "harry", "norm", "harry", "final", "harry"),
            Map.of(
                "queryTextSource", "query.final",
                "lexical", Map.of("enabled", true, "topKHint", 50),
                "vector", Map.of("enabled", false),
                "filters", List.of(
                    Map.of(
                        "and", List.of(
                            Map.of("scope", "CATALOG", "logicalField", "kdc_node_id", "op", "eq", "value", List.of(101, 102))
                        )
                    )
                )
            )
        );

        mockMvc.perform(post("/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(payload)))
            .andExpect(status().isOk());

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<Map<String, Object>>> filtersCaptor = ArgumentCaptor.forClass(List.class);
        verify(openSearchGateway).searchLexicalDetailed(
            eq("harry"),
            anyInt(),
            any(),
            any(),
            any(),
            any(),
            filtersCaptor.capture(),
            any(),
            anyBoolean()
        );
        boolean hasKdc = filtersCaptor.getValue().stream()
            .anyMatch(entry -> entry.containsKey("terms") && ((Map<String, Object>) entry.get("terms")).containsKey("kdc_node_id"));
        org.junit.jupiter.api.Assertions.assertTrue(hasKdc);
    }

    @Test
    void expandsPreferredLogicalFieldsWithNgramFallbacks() throws Exception {
        when(openSearchGateway.searchLexicalDetailed(eq("문화지도"), anyInt(), any(), any(), any(), any(), any(), any(), anyBoolean()))
            .thenReturn(new OpenSearchQueryResult(List.of("b1"), Map.of(), Map.of()));
        when(openSearchGateway.mgetSources(anyList(), any())).thenReturn(buildSources());

        Map<String, Object> payload = qcV11Payload(
            Map.of("raw", "문화지도", "norm", "문화지도", "final", "문화지도"),
            Map.of(
                "queryTextSource", "query.final",
                "lexical", Map.of("enabled", true, "topKHint", 50, "preferredLogicalFields", List.of("title_ko", "author_ko")),
                "vector", Map.of("enabled", false),
                "rerank", Map.of("enabled", false)
            )
        );

        mockMvc.perform(post("/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(payload)))
            .andExpect(status().isOk());

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<String>> fieldsCaptor = ArgumentCaptor.forClass(List.class);
        verify(openSearchGateway).searchLexicalDetailed(
            eq("문화지도"),
            anyInt(),
            any(),
            any(),
            any(),
            any(),
            any(),
            fieldsCaptor.capture(),
            anyBoolean()
        );
        List<String> fields = fieldsCaptor.getValue();
        org.junit.jupiter.api.Assertions.assertTrue(fields.contains("title_ko.ngram"));
        org.junit.jupiter.api.Assertions.assertTrue(fields.contains("authors.name_ko.ngram"));
    }

    @Test
    void appliesFallbackOnVectorError() throws Exception {
        when(openSearchGateway.searchLexicalDetailed(eq("harry"), anyInt(), any(), any(), any(), any(), any(), any(), anyBoolean()))
            .thenReturn(new OpenSearchQueryResult(List.of("b1"), Map.of(), Map.of()));
        when(openSearchGateway.searchVectorDetailed(anyList(), anyInt(), any(), any(), anyBoolean()))
            .thenThrow(new OpenSearchUnavailableException("vector down", new RuntimeException("timeout")));
        when(openSearchGateway.mgetSources(anyList(), any())).thenReturn(buildSources());

        Map<String, Object> payload = qcV11Payload(
            Map.of("raw", "harry", "norm", "harry", "final", "harry"),
            Map.of(
                "queryTextSource", "query.final",
                "lexical", Map.of("enabled", true, "topKHint", 50),
                "vector", Map.of("enabled", true, "topKHint", 50, "fusionHint", Map.of("method", "rrf", "k", 60)),
                "rerank", Map.of("enabled", false),
                "fallbackPolicy", List.of(
                    Map.of(
                        "id", "FB1_LEXICAL_ONLY",
                        "when", Map.of("onVectorError", true),
                        "mutations", Map.of("disable", List.of("vector", "rerank"), "useQueryTextSource", "query.norm")
                    )
                )
            )
        );

        mockMvc.perform(post("/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(payload)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.strategy").value("hybrid_rrf_v1_1_fallback_lexical"))
            .andExpect(jsonPath("$.debug.applied_fallback_id").value("FB1_LEXICAL_ONLY"));
    }

    @Test
    void usesAuthorRoutingDslWhenUnderstandingExists() throws Exception {
        when(openSearchGateway.searchLexicalByDslDetailed(any(), anyInt(), any(), any(), anyBoolean()))
            .thenReturn(new OpenSearchQueryResult(List.of("b1"), Map.of(), Map.of()));
        when(openSearchGateway.mgetSources(anyList(), any())).thenReturn(buildSources());

        Map<String, Object> payload = qcV11Payload(
            Map.of("raw", "author:김영하 데미안", "norm", "author:김영하 데미안", "final", "데미안"),
            Map.of(
                "queryTextSource", "query.final",
                "lexical", Map.of("enabled", true, "topKHint", 50),
                "vector", Map.of("enabled", false),
                "rerank", Map.of("enabled", false)
            )
        );
        @SuppressWarnings("unchecked")
        Map<String, Object> qc = (Map<String, Object>) payload.get("query_context_v1_1");
        qc.put(
            "understanding",
            Map.of(
                "entities",
                Map.of("author", List.of("김영하"), "title", List.of(), "series", List.of(), "publisher", List.of(), "isbn", List.of()),
                "constraints",
                Map.of("residualText", "데미안")
            )
        );

        mockMvc.perform(post("/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(payload)))
            .andExpect(status().isOk());

        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, Object>> dslCaptor = ArgumentCaptor.forClass(Map.class);
        verify(openSearchGateway).searchLexicalByDslDetailed(dslCaptor.capture(), anyInt(), any(), any(), anyBoolean());
        @SuppressWarnings("unchecked")
        Map<String, Object> bool = (Map<String, Object>) dslCaptor.getValue().get("bool");
        org.junit.jupiter.api.Assertions.assertNotNull(bool.get("must"));
    }

    @Test
    void retriesOnceWithEnhanceWhenZeroResults() throws Exception {
        when(openSearchGateway.searchLexicalDetailed(anyString(), anyInt(), any(), any(), any(), any(), any(), any(), anyBoolean()))
            .thenReturn(
                new OpenSearchQueryResult(List.of(), Map.of(), Map.of()),
                new OpenSearchQueryResult(List.of("b1"), Map.of(), Map.of())
            );
        when(openSearchGateway.mgetSources(anyList(), any())).thenReturn(buildSources());

        QueryEnhanceResponse enhanceResponse = new QueryEnhanceResponse();
        enhanceResponse.setDecision("RUN");
        enhanceResponse.setStrategy("REWRITE_ONLY");
        QueryEnhanceResponse.FinalQuery finalQuery = new QueryEnhanceResponse.FinalQuery();
        finalQuery.setText("harry potter");
        finalQuery.setSource("rewrite");
        enhanceResponse.setFinalQuery(finalQuery);
        when(queryServiceGateway.enhance(any(), anyInt(), any(), any(), any())).thenReturn(enhanceResponse);

        Map<String, Object> payload = qcV11Payload(
            Map.of("raw", "harry", "norm", "harry", "final", "harry"),
            Map.of(
                "queryTextSource", "query.final",
                "lexical", Map.of("enabled", true, "topKHint", 50),
                "vector", Map.of("enabled", false),
                "rerank", Map.of("enabled", false)
            )
        );

        mockMvc.perform(post("/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(payload)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.debug.enhance_applied").value(true));

        verify(queryServiceGateway).enhance(any(), anyInt(), any(), any(), any());
        verify(openSearchGateway, times(2))
            .searchLexicalDetailed(anyString(), anyInt(), any(), any(), any(), any(), any(), any(), anyBoolean());
    }

    private Map<String, Object> qcV11Payload(Map<String, Object> query, Map<String, Object> retrievalHints) {
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("schemaVersion", "qc.v1.1");
        meta.put("traceId", "trace_demo");
        meta.put("requestId", "req_demo");

        Map<String, Object> qc = new LinkedHashMap<>();
        qc.put("meta", meta);
        qc.put("query", query);
        qc.put("retrievalHints", retrievalHints);

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("query_context_v1_1", qc);
        payload.put("options", Map.of("size", 5, "from", 0));
        return payload;
    }

    private Map<String, com.fasterxml.jackson.databind.JsonNode> buildSources() {
        Map<String, com.fasterxml.jackson.databind.JsonNode> sources = new LinkedHashMap<>();
        ObjectNode node = objectMapper.createObjectNode();
        node.put("doc_id", "b1");
        node.put("title_ko", "Harry");
        node.putArray("authors").add("Author");
        sources.put("b1", node);
        return sources;
    }

    private Map<String, com.fasterxml.jackson.databind.JsonNode> buildSourcesForCategoryOrdering() {
        Map<String, com.fasterxml.jackson.databind.JsonNode> sources = new LinkedHashMap<>();
        ObjectNode hanja = objectMapper.createObjectNode();
        hanja.put("doc_id", "hanja");
        hanja.put("title_ko", "周易辭典");
        hanja.putArray("authors").add("Author A");
        sources.put("hanja", hanja);

        ObjectNode korean = objectMapper.createObjectNode();
        korean.put("doc_id", "korean");
        korean.put("title_ko", "한국철학 입문");
        korean.putArray("authors").add("Author B");
        sources.put("korean", korean);
        return sources;
    }
}
