package com.bsl.autocomplete.api;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bsl.autocomplete.api.dto.AutocompleteResponse;
import com.bsl.autocomplete.service.AutocompleteService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(AutocompleteController.class)
class AutocompleteControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private AutocompleteService autocompleteService;

    @Test
    void autocompleteRejectsMissingQuery() throws Exception {
        mockMvc.perform(get("/autocomplete"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error.code").value("bad_request"))
            .andExpect(jsonPath("$.trace_id").exists())
            .andExpect(jsonPath("$.request_id").exists());
    }

    @Test
    void autocompleteReturnsSuggestions() throws Exception {
        AutocompleteResponse response = new AutocompleteResponse();
        response.setTraceId("trace-1");
        response.setRequestId("req-1");
        response.setTookMs(5L);

        AutocompleteResponse.Suggestion suggestion = new AutocompleteResponse.Suggestion();
        suggestion.setText("harry potter");
        suggestion.setScore(0.9);
        suggestion.setSource("mvp");
        response.setSuggestions(List.of(suggestion));

        when(autocompleteService.autocomplete(eq("har"), eq(5), eq("trace-1"), eq("req-1")))
            .thenReturn(response);

        mockMvc.perform(get("/autocomplete")
                .param("q", "har")
                .param("size", "5")
                .header("x-trace-id", "trace-1")
                .header("x-request-id", "req-1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.trace_id").value("trace-1"))
            .andExpect(jsonPath("$.request_id").value("req-1"))
            .andExpect(jsonPath("$.suggestions[0].text").value("harry potter"))
            .andExpect(jsonPath("$.suggestions[0].score").value(0.9))
            .andExpect(jsonPath("$.suggestions[0].source").value("mvp"));
    }

    @Test
    void autocompleteClampsSize() throws Exception {
        AutocompleteResponse response = new AutocompleteResponse();
        response.setTraceId("trace-1");
        response.setRequestId("req-1");
        response.setSuggestions(List.of());

        when(autocompleteService.autocomplete(anyString(), eq(20), anyString(), anyString()))
            .thenReturn(response);

        mockMvc.perform(get("/autocomplete")
                .param("q", "har")
                .param("size", "200"))
            .andExpect(status().isOk());
    }
}
