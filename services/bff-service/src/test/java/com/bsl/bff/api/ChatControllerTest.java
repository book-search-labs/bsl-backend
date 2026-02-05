package com.bsl.bff.api;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bsl.bff.client.QueryServiceClient;
import com.bsl.bff.common.ApiExceptionHandler;
import com.bsl.bff.common.BffRequestContextFilter;
import com.bsl.bff.outbox.OutboxService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@ExtendWith(MockitoExtension.class)
class ChatControllerTest {
    @Mock
    private QueryServiceClient queryServiceClient;

    @Mock
    private OutboxService outboxService;

    private MockMvc mockMvc;
    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() {
        objectMapper = new ObjectMapper();
        ChatController controller = new ChatController(queryServiceClient, objectMapper, outboxService);
        mockMvc = MockMvcBuilders.standaloneSetup(controller)
            .setControllerAdvice(new ApiExceptionHandler())
            .addFilter(new BffRequestContextFilter())
            .build();
    }

    @Test
    void chatNonStreamUsesJsonDownstream() throws Exception {
        JsonNode responseNode = objectMapper.readTree(
            "{" +
                "\"version\":\"v1\"," +
                "\"trace_id\":\"trace_a\"," +
                "\"request_id\":\"req_a\"," +
                "\"status\":\"ok\"," +
                "\"answer\":{\"role\":\"assistant\",\"content\":\"hi\"}," +
                "\"sources\":[]," +
                "\"citations\":[\"chunk-1\"]" +
                "}"
        );
        when(queryServiceClient.chat(anyMap(), any())).thenReturn(responseNode);

        String body = "{" +
            "\"version\":\"v1\"," +
            "\"trace_id\":\"trace_1\"," +
            "\"request_id\":\"req_1\"," +
            "\"message\":{\"role\":\"user\",\"content\":\"hello\"}" +
            "}";

        mockMvc.perform(post("/chat")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.citations[0]").value("chunk-1"));

        verify(queryServiceClient).chat(anyMap(), any());
        verify(queryServiceClient, never()).chatStream(anyMap(), any(), any(SseEmitter.class));
    }

    @Test
    void chatStreamUsesStreamingDownstream() throws Exception {
        QueryServiceClient.ChatStreamResult streamResult = new QueryServiceClient.ChatStreamResult();
        streamResult.addCitation("chunk-1");
        when(queryServiceClient.chatStream(anyMap(), any(), any(SseEmitter.class))).thenReturn(streamResult);

        String body = "{" +
            "\"version\":\"v1\"," +
            "\"trace_id\":\"trace_1\"," +
            "\"request_id\":\"req_1\"," +
            "\"message\":{\"role\":\"user\",\"content\":\"hello\"}" +
            "}";

        mockMvc.perform(post("/chat")
                .param("stream", "true")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isOk());

        verify(queryServiceClient, timeout(1000)).chatStream(anyMap(), any(), any(SseEmitter.class));
        verify(queryServiceClient, never()).chat(anyMap(), any());
    }

    @Test
    void v1ChatAliasUsesNonStreamDownstream() throws Exception {
        JsonNode responseNode = objectMapper.readTree(
            "{"
                + "\"version\":\"v1\","
                + "\"trace_id\":\"trace_a\","
                + "\"request_id\":\"req_a\","
                + "\"status\":\"ok\","
                + "\"answer\":{\"role\":\"assistant\",\"content\":\"hi\"},"
                + "\"sources\":[],"
                + "\"citations\":[\"chunk-1\"]"
                + "}"
        );
        when(queryServiceClient.chat(anyMap(), any())).thenReturn(responseNode);

        String body = "{"
            + "\"version\":\"v1\","
            + "\"trace_id\":\"trace_1\","
            + "\"request_id\":\"req_1\","
            + "\"message\":{\"role\":\"user\",\"content\":\"hello\"}"
            + "}";

        mockMvc.perform(post("/v1/chat")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));

        verify(queryServiceClient).chat(anyMap(), any());
    }
}
