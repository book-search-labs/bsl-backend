package com.bsl.search;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bsl.search.api.SearchController;
import com.bsl.search.api.dto.BookHit;
import com.bsl.search.api.dto.SearchRequest;
import com.bsl.search.api.dto.SearchResponse;
import com.bsl.search.service.BookDetailResult;
import com.bsl.search.service.HybridSearchService;
import com.bsl.search.service.InvalidSearchRequestException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(SearchController.class)
class SearchControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private HybridSearchService hybridSearchService;

    @Test
    void healthReturnsOk() throws Exception {
        mockMvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void searchReturnsHits() throws Exception {
        SearchResponse response = new SearchResponse();
        response.setTraceId("trace-1");
        response.setRequestId("req-1");
        response.setTookMs(12L);
        response.setStrategy("hybrid_rrf_v1");

        BookHit.Source source = new BookHit.Source();
        source.setTitleKo("Sample");

        BookHit hit = new BookHit();
        hit.setDocId("b1");
        hit.setScore(0.5);
        hit.setRank(1);
        hit.setSource(source);
        response.setHits(List.of(hit));

        when(hybridSearchService.search(any(), anyString(), anyString())).thenReturn(response);

        SearchRequest request = new SearchRequest();
        SearchRequest.Query query = new SearchRequest.Query();
        query.setRaw("harry");
        request.setQuery(query);

        mockMvc.perform(post("/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(request)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.trace_id").value("trace-1"))
            .andExpect(jsonPath("$.hits[0].doc_id").value("b1"))
            .andExpect(jsonPath("$.hits[0].source.title_ko").value("Sample"));
    }

    @Test
    void searchRejectsMissingQuery() throws Exception {
        when(hybridSearchService.search(any(), anyString(), anyString()))
            .thenThrow(new InvalidSearchRequestException("query text is required"));

        mockMvc.perform(post("/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error.code").value("bad_request"));
    }

    @Test
    void getBookByIdReturnsDoc() throws Exception {
        com.bsl.search.api.dto.BookDetailResponse response = new com.bsl.search.api.dto.BookDetailResponse();
        response.setDocId("b1");
        response.setTraceId("trace-1");
        response.setRequestId("req-1");
        response.setTookMs(5L);

        BookHit.Source source = new BookHit.Source();
        source.setTitleKo("Sample");
        response.setSource(source);

        BookDetailResult result = new BookDetailResult(response, "etag-1", false, 0L, 60000L, 60);
        when(hybridSearchService.getBookById(eq("b1"), eq("trace-1"), eq("req-1"))).thenReturn(result);

        mockMvc.perform(get("/books/b1")
                .header("x-trace-id", "trace-1")
                .header("x-request-id", "req-1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.doc_id").value("b1"))
            .andExpect(jsonPath("$.source.title_ko").value("Sample"))
            .andExpect(jsonPath("$.trace_id").value("trace-1"))
            .andExpect(jsonPath("$.request_id").value("req-1"));

        verify(hybridSearchService).getBookById(eq("b1"), eq("trace-1"), eq("req-1"));
    }

    @Test
    void getBookByIdReturnsNotFound() throws Exception {
        when(hybridSearchService.getBookById(anyString(), anyString(), anyString()))
            .thenReturn(null);

        mockMvc.perform(get("/books/missing"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.error.code").value("not_found"))
            .andExpect(jsonPath("$.trace_id").exists())
            .andExpect(jsonPath("$.request_id").exists());
    }
}
