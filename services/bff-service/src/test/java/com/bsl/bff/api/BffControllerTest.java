package com.bsl.bff.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bsl.bff.client.AutocompleteServiceClient;
import com.bsl.bff.client.ReadyCheckService;
import com.bsl.bff.common.ApiExceptionHandler;
import com.bsl.bff.common.BffRequestContextFilter;
import com.bsl.bff.outbox.OutboxService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers = {HealthController.class, AutocompleteController.class})
@Import({BffRequestContextFilter.class, ApiExceptionHandler.class})
class BffControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ReadyCheckService readyCheckService;

    @MockBean
    private AutocompleteServiceClient autocompleteServiceClient;

    @MockBean
    private OutboxService outboxService;

    @Test
    void healthIncludesRequestId() throws Exception {
        mockMvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.request_id").exists())
            .andExpect(jsonPath("$.trace_id").exists());
    }

    @Test
    void autocompleteEmptyQueryReturnsEmptySuggestions() throws Exception {
        mockMvc.perform(get("/autocomplete").param("q", ""))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.request_id").exists())
            .andExpect(jsonPath("$.trace_id").exists())
            .andExpect(jsonPath("$.suggestions").isArray())
            .andExpect(jsonPath("$.suggestions").isEmpty());
    }
}
