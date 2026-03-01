package com.bsl.bff.api;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bsl.bff.audit.AuditLogRepository;
import com.bsl.bff.client.AutocompleteServiceClient;
import com.bsl.bff.client.dto.AutocompleteServiceResponse;
import com.bsl.bff.client.ReadyCheckService;
import com.bsl.bff.common.ApiExceptionHandler;
import com.bsl.bff.common.BffRequestContextFilter;
import com.bsl.bff.outbox.OutboxService;
import com.bsl.bff.security.PiiMasker;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.filter.OncePerRequestFilter;

@WebMvcTest(
    controllers = {HealthController.class, AutocompleteController.class},
    excludeFilters = @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = OncePerRequestFilter.class)
)
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

    @MockBean
    private AuditLogRepository auditLogRepository;

    @MockBean
    private PiiMasker piiMasker;

    @Test
    void healthIncludesRequestId() throws Exception {
        mockMvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.request_id").exists())
            .andExpect(jsonPath("$.trace_id").exists());
    }

    @Test
    void autocompleteEmptyQueryDelegatesToService() throws Exception {
        AutocompleteServiceResponse.Suggestion suggestion = new AutocompleteServiceResponse.Suggestion();
        suggestion.setText("베스트셀러");
        suggestion.setScore(1.0d);
        suggestion.setSource("trending");

        AutocompleteServiceResponse serviceResponse = new AutocompleteServiceResponse();
        serviceResponse.setTookMs(7L);
        serviceResponse.setSuggestions(List.of(suggestion));

        when(autocompleteServiceClient.autocomplete(eq(""), eq(10), any())).thenReturn(serviceResponse);

        mockMvc.perform(get("/autocomplete").param("q", ""))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.request_id").exists())
            .andExpect(jsonPath("$.trace_id").exists())
            .andExpect(jsonPath("$.suggestions").isArray())
            .andExpect(jsonPath("$.suggestions[0].text").value("베스트셀러"));

        verify(autocompleteServiceClient).autocomplete(eq(""), eq(10), any());
    }
}
