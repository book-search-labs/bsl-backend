package com.bsl.bff.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bsl.bff.common.ApiExceptionHandler;
import com.bsl.bff.common.BffRequestContextFilter;
import com.bsl.bff.outbox.OutboxService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

@ExtendWith(MockitoExtension.class)
class SearchEventControllerTest {
    @Mock
    private OutboxService outboxService;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        SearchEventController controller = new SearchEventController(outboxService);
        mockMvc = MockMvcBuilders.standaloneSetup(controller)
            .setControllerAdvice(new ApiExceptionHandler())
            .addFilter(new BffRequestContextFilter())
            .build();
    }

    @Test
    void searchClickReturnsAck() throws Exception {
        String body = "{"
            + "\"imp_id\":\"imp_123\"," 
            + "\"doc_id\":\"book_1\"," 
            + "\"position\":1,"
            + "\"query_hash\":\"hash_1\""
            + "}";

        mockMvc.perform(post("/search/click")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.request_id").exists())
            .andExpect(jsonPath("$.trace_id").exists());
    }

    @Test
    void searchClickV1AliasReturnsAck() throws Exception {
        String body = "{"
            + "\"imp_id\":\"imp_123\"," 
            + "\"doc_id\":\"book_1\"," 
            + "\"position\":1,"
            + "\"query_hash\":\"hash_1\""
            + "}";

        mockMvc.perform(post("/v1/search/click")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void searchDwellReturnsAck() throws Exception {
        String body = "{"
            + "\"imp_id\":\"imp_123\"," 
            + "\"doc_id\":\"book_1\"," 
            + "\"position\":1,"
            + "\"query_hash\":\"hash_1\"," 
            + "\"dwell_ms\":1200"
            + "}";

        mockMvc.perform(post("/search/dwell")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.request_id").exists())
            .andExpect(jsonPath("$.trace_id").exists());
    }
}
