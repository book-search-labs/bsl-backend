package com.bsl.bff.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bsl.bff.common.ApiExceptionHandler;
import com.bsl.bff.common.BffRequestContextFilter;
import com.bsl.bff.outbox.OutboxService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers = {SearchEventController.class})
@Import({BffRequestContextFilter.class, ApiExceptionHandler.class})
class SearchEventControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OutboxService outboxService;

    @Test
    void searchClickReturnsAck() throws Exception {
        String body = "{" +
            "\"imp_id\":\"imp_123\"," +
            "\"doc_id\":\"book_1\"," +
            "\"position\":1," +
            "\"query_hash\":\"hash_1\"" +
            "}";

        mockMvc.perform(post("/search/click")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.request_id").exists())
            .andExpect(jsonPath("$.trace_id").exists());
    }

    @Test
    void searchDwellReturnsAck() throws Exception {
        String body = "{" +
            "\"imp_id\":\"imp_123\"," +
            "\"doc_id\":\"book_1\"," +
            "\"position\":1," +
            "\"query_hash\":\"hash_1\"," +
            "\"dwell_ms\":1200" +
            "}";

        mockMvc.perform(post("/search/dwell")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.request_id").exists())
            .andExpect(jsonPath("$.trace_id").exists());
    }
}
