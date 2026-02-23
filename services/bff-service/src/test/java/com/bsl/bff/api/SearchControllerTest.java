package com.bsl.bff.api;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.bff.api.dto.BffSearchRequest;
import com.bsl.bff.api.dto.BffSearchResponse;
import com.bsl.bff.authority.AgentAliasService;
import com.bsl.bff.budget.BudgetProperties;
import com.bsl.bff.client.QueryServiceClient;
import com.bsl.bff.client.SearchServiceClient;
import com.bsl.bff.client.dto.SearchServiceResponse;
import com.bsl.bff.outbox.OutboxService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class SearchControllerTest {
    @Mock
    private QueryServiceClient queryServiceClient;

    @Mock
    private SearchServiceClient searchServiceClient;

    @Mock
    private OutboxService outboxService;

    @Mock
    private AgentAliasService aliasService;

    private SearchController controller;
    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() {
        objectMapper = new ObjectMapper();
        controller = new SearchController(
            queryServiceClient,
            searchServiceClient,
            outboxService,
            new BudgetProperties(),
            aliasService
        );
    }

    @Test
    void retriesRawQueryWhenAutoQueryContextReturnsNoHits() throws Exception {
        BffSearchRequest request = requestWithRawQuery("영어교육");
        JsonNode autoQc = objectMapper.readTree(
            "{"
                + "\"meta\":{\"schemaVersion\":\"qc.v1.1\"},"
                + "\"query\":{\"raw\":\"영어교육\",\"norm\":\"영어교육\",\"final\":\"영어교육\"},"
                + "\"retrievalHints\":{}"
                + "}"
        );
        when(queryServiceClient.fetchQueryContext(eq("영어교육"), any())).thenReturn(autoQc);

        SearchServiceResponse empty = new SearchServiceResponse();
        empty.setTotal(0);
        empty.setHits(List.of());

        SearchServiceResponse recovered = new SearchServiceResponse();
        recovered.setTotal(1);
        recovered.setHits(List.of(hit("nlk:CDM200900003", "초등영어교육의 영미문화지도에 관한 연구")));

        when(searchServiceClient.search(any(), any())).thenReturn(empty, recovered);

        BffSearchResponse response = controller.search(request, null, null);

        assertNotNull(response);
        assertEquals(1, response.getTotal());
        assertNotNull(response.getHits());
        assertEquals(1, response.getHits().size());
        assertEquals("초등영어교육의 영미문화지도에 관한 연구", response.getHits().get(0).getTitle());

        ArgumentCaptor<com.bsl.bff.client.dto.DownstreamSearchRequest> requestCaptor =
            ArgumentCaptor.forClass(com.bsl.bff.client.dto.DownstreamSearchRequest.class);
        verify(searchServiceClient, times(2)).search(requestCaptor.capture(), any());

        List<com.bsl.bff.client.dto.DownstreamSearchRequest> captured = requestCaptor.getAllValues();
        assertNotNull(captured.get(0).getQueryContextV11());
        assertNull(captured.get(1).getQueryContextV11());
        assertEquals("영어교육", captured.get(1).getQuery().getRaw());
    }

    private BffSearchRequest requestWithRawQuery(String rawQuery) {
        BffSearchRequest request = new BffSearchRequest();
        BffSearchRequest.Query query = new BffSearchRequest.Query();
        query.setRaw(rawQuery);
        request.setQuery(query);

        BffSearchRequest.Options options = new BffSearchRequest.Options();
        options.setSize(20);
        options.setFrom(0);
        options.setEnableVector(true);
        request.setOptions(options);
        return request;
    }

    private SearchServiceResponse.BookHit hit(String docId, String title) {
        SearchServiceResponse.Source source = new SearchServiceResponse.Source();
        source.setTitleKo(title);
        source.setAuthors(List.of("한은경"));
        source.setPublisherName("釜山外國語大學校");
        source.setIssuedYear(2008);

        SearchServiceResponse.BookHit hit = new SearchServiceResponse.BookHit();
        hit.setDocId(docId);
        hit.setScore(1.0d);
        hit.setSource(source);
        return hit;
    }
}
