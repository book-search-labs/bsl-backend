package com.bsl.search.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

import com.bsl.search.api.dto.Options;
import com.bsl.search.api.dto.SearchRequest;
import com.bsl.search.api.dto.SearchResponse;
import com.bsl.search.embed.ToyEmbedder;
import com.bsl.search.opensearch.OpenSearchGateway;
import com.bsl.search.ranking.RankingGateway;
import com.bsl.search.ranking.RankingUnavailableException;
import com.bsl.search.ranking.dto.RerankResponse;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class HybridSearchServiceRankingTest {

    @Mock
    private OpenSearchGateway openSearchGateway;

    @Mock
    private RankingGateway rankingGateway;

    private HybridSearchService service;
    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() {
        service = new HybridSearchService(openSearchGateway, new ToyEmbedder(), rankingGateway);
        objectMapper = new ObjectMapper();
    }

    @Test
    void searchUsesRankingOrderWhenAvailable() {
        SearchRequest request = buildRequest("harry");
        when(openSearchGateway.searchLexical(eq("harry"), anyInt()))
            .thenReturn(List.of("b1", "b2"));
        when(openSearchGateway.mgetSources(anyList())).thenReturn(buildSources());

        RerankResponse rerankResponse = new RerankResponse();
        RerankResponse.Hit hit1 = new RerankResponse.Hit();
        hit1.setDocId("b2");
        hit1.setScore(0.9);
        hit1.setRank(1);
        RerankResponse.Hit hit2 = new RerankResponse.Hit();
        hit2.setDocId("b1");
        hit2.setScore(0.8);
        hit2.setRank(2);
        rerankResponse.setHits(List.of(hit1, hit2));

        when(rankingGateway.rerank(eq("harry"), anyList(), anyInt(), anyString(), anyString()))
            .thenReturn(rerankResponse);

        SearchResponse response = service.search(request, "trace-1", "req-1");

        assertTrue(response.isRankingApplied());
        assertEquals(2, response.getHits().size());
        assertEquals("b2", response.getHits().get(0).getDocId());
        assertEquals("b1", response.getHits().get(1).getDocId());
        assertEquals(0.9, response.getHits().get(0).getDebug().getRankingScore());
    }

    @Test
    void searchFallsBackToRrfWhenRankingUnavailable() {
        SearchRequest request = buildRequest("harry");
        when(openSearchGateway.searchLexical(eq("harry"), anyInt()))
            .thenReturn(List.of("b1", "b2"));
        when(openSearchGateway.mgetSources(anyList())).thenReturn(buildSources());
        when(rankingGateway.rerank(eq("harry"), anyList(), anyInt(), anyString(), anyString()))
            .thenThrow(new RankingUnavailableException("down", new RuntimeException("timeout")));

        SearchResponse response = service.search(request, "trace-1", "req-1");

        assertFalse(response.isRankingApplied());
        assertEquals(2, response.getHits().size());
        assertEquals("b1", response.getHits().get(0).getDocId());
        assertEquals("b2", response.getHits().get(1).getDocId());
    }

    private SearchRequest buildRequest(String raw) {
        SearchRequest request = new SearchRequest();
        SearchRequest.Query query = new SearchRequest.Query();
        query.setRaw(raw);
        request.setQuery(query);

        Options options = new Options();
        options.setSize(2);
        options.setFrom(0);
        options.setEnableVector(false);
        request.setOptions(options);
        return request;
    }

    private Map<String, JsonNode> buildSources() {
        Map<String, JsonNode> sources = new LinkedHashMap<>();

        ObjectNode b1 = objectMapper.createObjectNode();
        b1.put("doc_id", "b1");
        b1.put("title_ko", "One");
        b1.put("issued_year", 1999);
        b1.put("volume", 1);
        b1.putArray("edition_labels").add("recover");
        b1.putArray("authors").add("Author 1");
        sources.put("b1", b1);

        ObjectNode b2 = objectMapper.createObjectNode();
        b2.put("doc_id", "b2");
        b2.put("title_ko", "Two");
        b2.put("issued_year", 2000);
        b2.put("volume", 2);
        b2.putArray("edition_labels");
        b2.putArray("authors").add("Author 2");
        sources.put("b2", b2);

        return sources;
    }
}
