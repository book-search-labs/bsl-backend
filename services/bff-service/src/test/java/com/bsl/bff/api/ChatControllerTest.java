package com.bsl.bff.api;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bsl.bff.client.QueryServiceClient;
import com.bsl.bff.common.ApiExceptionHandler;
import com.bsl.bff.common.BffRequestContextFilter;
import com.bsl.bff.outbox.OutboxService;
import com.bsl.bff.security.AuthContext;
import com.bsl.bff.security.AuthContextHolder;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
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

    @AfterEach
    void tearDownAuthContext() {
        AuthContextHolder.clear();
    }

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
            "\"message\":{\"role\":\"user\",\"content\":\"refund status\"}" +
            "}";

        mockMvc.perform(post("/chat")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.citations[0]").value("chunk-1"));

        verify(queryServiceClient).chat(anyMap(), any());
        verify(queryServiceClient, never()).chatStream(anyMap(), any(), any(SseEmitter.class));
        ArgumentCaptor<java.util.Map<String, Object>> payloadCaptor = ArgumentCaptor.forClass(java.util.Map.class);
        verify(outboxService).record(eq("chat_response_v1"), eq("chat_session"), any(), payloadCaptor.capture());
        assertEquals("R2", payloadCaptor.getValue().get("risk_band"));
    }

    @Test
    void chatNormalizesSessionIdAndInjectsAuthenticatedUser() throws Exception {
        AuthContextHolder.set(new AuthContext("101", null));
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

        String body = "{"
            + "\"version\":\"v1\","
            + "\"session_id\":\"thread-1\","
            + "\"message\":{\"role\":\"user\",\"content\":\"hello\"}"
            + "}";

        mockMvc.perform(post("/chat")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));

        ArgumentCaptor<Map<String, Object>> payloadCaptor = ArgumentCaptor.forClass(Map.class);
        verify(queryServiceClient).chat(payloadCaptor.capture(), any());
        Map<String, Object> payload = payloadCaptor.getValue();
        assertEquals("u:101:thread-1", payload.get("session_id"));
        Map<String, Object> client = (Map<String, Object>) payload.get("client");
        assertEquals("101", client.get("user_id"));
    }

    @Test
    void chatRejectsCrossUserSessionWhenAuthenticated() throws Exception {
        AuthContextHolder.set(new AuthContext("101", null));
        String body = "{"
            + "\"version\":\"v1\","
            + "\"session_id\":\"u:999:default\","
            + "\"message\":{\"role\":\"user\",\"content\":\"hello\"}"
            + "}";

        mockMvc.perform(post("/chat")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.error.code").value("forbidden"));

        verify(queryServiceClient, never()).chat(anyMap(), any());
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

    @Test
    void chatSessionStateProxyReturnsQueryServicePayload() throws Exception {
        JsonNode responseNode = objectMapper.readTree(
            "{"
                + "\"version\":\"v1\","
                + "\"trace_id\":\"trace_a\","
                + "\"request_id\":\"req_a\","
                + "\"status\":\"ok\","
                + "\"session\":{"
                + "\"session_id\":\"u:101:default\","
                + "\"fallback_count\":2,"
                + "\"fallback_escalation_threshold\":3,"
                + "\"escalation_ready\":false,"
                + "\"recommended_action\":\"RETRY\","
                + "\"recommended_message\":\"잠시 후 다시 시도해 주세요.\","
                + "\"unresolved_context\":null"
                + "}"
                + "}"
        );
        when(queryServiceClient.chatSessionState(eq("u:101:default"), any())).thenReturn(responseNode);

        mockMvc.perform(get("/chat/session/state")
                .param("session_id", "u:101:default"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.session.session_id").value("u:101:default"))
            .andExpect(jsonPath("$.session.recommended_action").value("RETRY"));
    }

    @Test
    void chatSessionStateRejectsCrossUserSessionWhenAuthenticated() throws Exception {
        AuthContextHolder.set(new AuthContext("101", null));

        mockMvc.perform(get("/chat/session/state")
                .param("session_id", "u:999:default"))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.error.code").value("forbidden"));

        verify(queryServiceClient, never()).chatSessionState(any(), any());
    }

    @Test
    void chatSessionStateNormalizesLegacySessionIdForAuthenticatedUser() throws Exception {
        AuthContextHolder.set(new AuthContext("101", null));
        JsonNode responseNode = objectMapper.readTree(
            "{"
                + "\"version\":\"v1\","
                + "\"trace_id\":\"trace_a\","
                + "\"request_id\":\"req_a\","
                + "\"status\":\"ok\","
                + "\"session\":{"
                + "\"session_id\":\"u:101:thread-1\","
                + "\"fallback_count\":0,"
                + "\"fallback_escalation_threshold\":3,"
                + "\"escalation_ready\":false,"
                + "\"recommended_action\":\"NONE\","
                + "\"recommended_message\":\"현재 챗봇 세션 상태는 정상입니다.\","
                + "\"unresolved_context\":null"
                + "}"
                + "}"
        );
        when(queryServiceClient.chatSessionState(eq("u:101:thread-1"), any())).thenReturn(responseNode);

        mockMvc.perform(get("/chat/session/state")
                .param("session_id", "thread-1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.session.session_id").value("u:101:thread-1"));
    }

    @Test
    void chatSessionStateRequiresSessionId() throws Exception {
        mockMvc.perform(get("/chat/session/state"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error.code").value("bad_request"));

        verify(queryServiceClient, never()).chatSessionState(any(), any());
    }

    @Test
    void v1ChatSessionStateAliasUsesQueryServiceProxy() throws Exception {
        JsonNode responseNode = objectMapper.readTree(
            "{"
                + "\"version\":\"v1\","
                + "\"trace_id\":\"trace_a\","
                + "\"request_id\":\"req_a\","
                + "\"status\":\"ok\","
                + "\"session\":{"
                + "\"session_id\":\"u:201:default\","
                + "\"fallback_count\":0,"
                + "\"fallback_escalation_threshold\":3,"
                + "\"escalation_ready\":false,"
                + "\"recommended_action\":\"NONE\","
                + "\"recommended_message\":\"현재 챗봇 세션 상태는 정상입니다.\","
                + "\"unresolved_context\":null"
                + "}"
                + "}"
        );
        when(queryServiceClient.chatSessionState(eq("u:201:default"), any())).thenReturn(responseNode);

        mockMvc.perform(get("/v1/chat/session/state")
                .param("session_id", "u:201:default"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.session.session_id").value("u:201:default"));
    }

    @Test
    void chatSessionResetProxyReturnsQueryServicePayload() throws Exception {
        JsonNode responseNode = objectMapper.readTree(
            "{"
                + "\"version\":\"v1\","
                + "\"trace_id\":\"trace_a\","
                + "\"request_id\":\"req_a\","
                + "\"status\":\"ok\","
                + "\"session\":{"
                + "\"session_id\":\"u:101:default\","
                + "\"reset_applied\":true,"
                + "\"previous_fallback_count\":3,"
                + "\"previous_unresolved_context\":true,"
                + "\"reset_at_ms\":1760000100000"
                + "}"
                + "}"
        );
        when(queryServiceClient.resetChatSession(eq("u:101:default"), any())).thenReturn(responseNode);

        mockMvc.perform(post("/chat/session/reset")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"session_id\":\"u:101:default\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.session.reset_applied").value(true))
            .andExpect(jsonPath("$.session.previous_fallback_count").value(3));
    }

    @Test
    void chatSessionResetRequiresSessionId() throws Exception {
        mockMvc.perform(post("/chat/session/reset")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error.code").value("bad_request"));

        verify(queryServiceClient, never()).resetChatSession(any(), any());
    }

    @Test
    void chatSessionResetRejectsCrossUserSessionWhenAuthenticated() throws Exception {
        AuthContextHolder.set(new AuthContext("101", null));

        mockMvc.perform(post("/chat/session/reset")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"session_id\":\"u:999:default\"}"))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.error.code").value("forbidden"));

        verify(queryServiceClient, never()).resetChatSession(any(), any());
    }

    @Test
    void v1ChatSessionResetAliasUsesQueryServiceProxy() throws Exception {
        JsonNode responseNode = objectMapper.readTree(
            "{"
                + "\"version\":\"v1\","
                + "\"trace_id\":\"trace_a\","
                + "\"request_id\":\"req_a\","
                + "\"status\":\"ok\","
                + "\"session\":{"
                + "\"session_id\":\"u:201:default\","
                + "\"reset_applied\":true,"
                + "\"previous_fallback_count\":1,"
                + "\"previous_unresolved_context\":false,"
                + "\"reset_at_ms\":1760000200000"
                + "}"
                + "}"
        );
        when(queryServiceClient.resetChatSession(eq("u:201:default"), any())).thenReturn(responseNode);

        mockMvc.perform(post("/v1/chat/session/reset")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"session_id\":\"u:201:default\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.session.reset_applied").value(true))
            .andExpect(jsonPath("$.session.previous_fallback_count").value(1));
    }

    @Test
    void chatFeedbackWritesOutboxEvent() throws Exception {
        String body = "{"
            + "\"version\":\"v1\","
            + "\"session_id\":\"conv-1\","
            + "\"message_id\":\"msg-1\","
            + "\"rating\":\"up\","
            + "\"flag_hallucination\":false,"
            + "\"flag_insufficient\":false"
            + "}";

        mockMvc.perform(post("/chat/feedback")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));

        ArgumentCaptor<Map<String, Object>> payloadCaptor = ArgumentCaptor.forClass(Map.class);
        verify(outboxService).record(eq("chat_feedback_v1"), eq("chat_message"), eq("msg-1"), payloadCaptor.capture());
        Map<String, Object> payload = payloadCaptor.getValue();
        assertEquals("conv-1", payload.get("session_id"));
        assertEquals("up", payload.get("rating"));
        assertEquals("anonymous", payload.get("auth_mode"));
    }

    @Test
    void chatFeedbackNormalizesLegacySessionForAuthenticatedUser() throws Exception {
        AuthContextHolder.set(new AuthContext("101", null));
        String body = "{"
            + "\"version\":\"v1\","
            + "\"session_id\":\"thread-2\","
            + "\"message_id\":\"msg-2\","
            + "\"rating\":\"DOWN\""
            + "}";

        mockMvc.perform(post("/chat/feedback")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));

        ArgumentCaptor<Map<String, Object>> payloadCaptor = ArgumentCaptor.forClass(Map.class);
        verify(outboxService).record(eq("chat_feedback_v1"), eq("chat_message"), eq("msg-2"), payloadCaptor.capture());
        Map<String, Object> payload = payloadCaptor.getValue();
        assertEquals("u:101:thread-2", payload.get("session_id"));
        assertEquals("down", payload.get("rating"));
        assertEquals("101", payload.get("actor_user_id"));
        assertEquals("user", payload.get("auth_mode"));
    }

    @Test
    void chatFeedbackRejectsCrossUserSessionWhenAuthenticated() throws Exception {
        AuthContextHolder.set(new AuthContext("101", null));
        String body = "{"
            + "\"version\":\"v1\","
            + "\"session_id\":\"u:999:thread-3\","
            + "\"rating\":\"down\""
            + "}";

        mockMvc.perform(post("/chat/feedback")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.error.code").value("forbidden"));

        verify(outboxService, never()).record(any(), any(), any(), any());
    }

    @Test
    void chatFeedbackRejectsInvalidRating() throws Exception {
        String body = "{"
            + "\"version\":\"v1\","
            + "\"session_id\":\"conv-2\","
            + "\"rating\":\"meh\""
            + "}";

        mockMvc.perform(post("/chat/feedback")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error.code").value("bad_request"));

        verify(outboxService, never()).record(any(), any(), any(), any());
    }

    @Test
    void chatRecommendExperimentSnapshotRequiresAdmin() throws Exception {
        mockMvc.perform(get("/chat/recommend/experiment"))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.error.code").value("forbidden"));

        verify(queryServiceClient, never()).chatRecommendExperimentSnapshot(any());
    }

    @Test
    void chatRecommendExperimentSnapshotProxyForAdmin() throws Exception {
        AuthContextHolder.set(new AuthContext("101", "1"));
        JsonNode responseNode = objectMapper.readTree(
            "{"
                + "\"version\":\"v1\","
                + "\"trace_id\":\"trace_a\","
                + "\"request_id\":\"req_a\","
                + "\"status\":\"ok\","
                + "\"experiment\":{"
                + "\"enabled\":true,"
                + "\"auto_disabled\":false,"
                + "\"total\":15,"
                + "\"blocked\":3,"
                + "\"block_rate\":0.2"
                + "}"
                + "}"
        );
        when(queryServiceClient.chatRecommendExperimentSnapshot(any())).thenReturn(responseNode);

        mockMvc.perform(get("/chat/recommend/experiment"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.experiment.total").value(15));
    }

    @Test
    void v1ChatRecommendExperimentSnapshotProxyForAdmin() throws Exception {
        AuthContextHolder.set(new AuthContext("101", "1"));
        JsonNode responseNode = objectMapper.readTree(
            "{"
                + "\"version\":\"v1\","
                + "\"trace_id\":\"trace_a\","
                + "\"request_id\":\"req_a\","
                + "\"status\":\"ok\","
                + "\"experiment\":{"
                + "\"enabled\":true,"
                + "\"auto_disabled\":false,"
                + "\"total\":11,"
                + "\"blocked\":2,"
                + "\"block_rate\":0.18"
                + "}"
                + "}"
        );
        when(queryServiceClient.chatRecommendExperimentSnapshot(any())).thenReturn(responseNode);

        mockMvc.perform(get("/v1/chat/recommend/experiment"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.experiment.total").value(11));
    }

    @Test
    void chatRecommendExperimentResetRequiresAdmin() throws Exception {
        mockMvc.perform(post("/chat/recommend/experiment/reset")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.error.code").value("forbidden"));

        verify(queryServiceClient, never()).resetChatRecommendExperiment(any());
    }

    @Test
    void chatRecommendExperimentResetProxyForAdmin() throws Exception {
        AuthContextHolder.set(new AuthContext("101", "1"));
        JsonNode responseNode = objectMapper.readTree(
            "{"
                + "\"version\":\"v1\","
                + "\"trace_id\":\"trace_a\","
                + "\"request_id\":\"req_a\","
                + "\"status\":\"ok\","
                + "\"reset\":{"
                + "\"reset_applied\":true,"
                + "\"before\":{\"total\":15},"
                + "\"after\":{\"total\":0}"
                + "}"
                + "}"
        );
        when(queryServiceClient.resetChatRecommendExperiment(any())).thenReturn(responseNode);

        mockMvc.perform(post("/chat/recommend/experiment/reset")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.reset.reset_applied").value(true))
            .andExpect(jsonPath("$.reset.after.total").value(0));
    }

    @Test
    void v1ChatRecommendExperimentResetProxyForAdmin() throws Exception {
        AuthContextHolder.set(new AuthContext("101", "1"));
        JsonNode responseNode = objectMapper.readTree(
            "{"
                + "\"version\":\"v1\","
                + "\"trace_id\":\"trace_a\","
                + "\"request_id\":\"req_a\","
                + "\"status\":\"ok\","
                + "\"reset\":{"
                + "\"reset_applied\":true,"
                + "\"before\":{\"total\":9},"
                + "\"after\":{\"total\":0}"
                + "}"
                + "}"
        );
        when(queryServiceClient.resetChatRecommendExperiment(any())).thenReturn(responseNode);

        mockMvc.perform(post("/v1/chat/recommend/experiment/reset")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.reset.reset_applied").value(true))
            .andExpect(jsonPath("$.reset.before.total").value(9));
    }
}
