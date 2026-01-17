package com.bsl.search;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bsl.search.opensearch.OpenSearchGateway;
import com.bsl.search.opensearch.OpenSearchUnavailableException;
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

    @Test
    void acceptsQcV11AndPropagatesIds() throws Exception {
        when(openSearchGateway.searchLexical(eq("harry"), anyInt(), any(), any(), any(), any(), any(), any()))
            .thenReturn(List.of("b1"));
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
        when(openSearchGateway.searchLexical(eq("harry"), anyInt(), any(), any(), any(), any(), any(), any()))
            .thenReturn(List.of("b1"));
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
        verify(openSearchGateway).searchLexical(eq("harry"), anyInt(), any(), any(), any(), any(), filtersCaptor.capture(), any());
        boolean hasVolume = filtersCaptor.getValue().stream()
            .anyMatch(entry -> entry.containsKey("term") && ((Map<String, Object>) entry.get("term")).containsKey("volume"));
        org.junit.jupiter.api.Assertions.assertTrue(hasVolume);
    }

    @Test
    void appliesFallbackOnVectorError() throws Exception {
        when(openSearchGateway.searchLexical(eq("harry"), anyInt(), any(), any(), any(), any(), any(), any()))
            .thenReturn(List.of("b1"));
        when(openSearchGateway.searchVector(anyList(), anyInt(), any(), any()))
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
}
