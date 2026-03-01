package com.bsl.bff.api;

import com.bsl.bff.api.dto.BffAckResponse;
import com.bsl.bff.api.dto.BffChatFeedbackRequest;
import com.bsl.bff.api.dto.BffChatRequest;
import com.bsl.bff.api.dto.BffChatResponse;
import com.bsl.bff.api.dto.BffChatSource;
import com.bsl.bff.budget.BudgetContext;
import com.bsl.bff.budget.BudgetContextHolder;
import com.bsl.bff.client.QueryServiceClient;
import com.bsl.bff.client.QueryServiceClient.ChatStreamResult;
import com.bsl.bff.common.BadRequestException;
import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.outbox.OutboxService;
import com.bsl.bff.security.AuthContext;
import com.bsl.bff.security.AuthContextHolder;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping({"/chat", "/v1/chat"})
public class ChatController {
    private static final Pattern USER_SESSION_PATTERN = Pattern.compile("^u:([^:]+)(?::|$)");
    private static final List<String> HIGH_RISK_KEYWORDS = List.of(
        "주문", "결제", "환불", "취소", "배송", "주소",
        "payment", "refund", "cancel", "shipping", "address"
    );

    private final QueryServiceClient queryServiceClient;
    private final ObjectMapper objectMapper;
    private final OutboxService outboxService;

    public ChatController(QueryServiceClient queryServiceClient, ObjectMapper objectMapper, OutboxService outboxService) {
        this.queryServiceClient = queryServiceClient;
        this.objectMapper = objectMapper;
        this.outboxService = outboxService;
    }

    @PostMapping
    public ResponseEntity<?> chat(
        @RequestBody(required = false) BffChatRequest request,
        @RequestParam(value = "stream", required = false) Boolean stream
    ) {
        if (request == null || request.getMessage() == null || request.getMessage().getContent() == null) {
            throw new BadRequestException("message is required");
        }
        BudgetContext budget = BudgetContextHolder.get();
        if (budget != null && budget.isExceeded()) {
            throw new DownstreamException(org.springframework.http.HttpStatus.GATEWAY_TIMEOUT, "budget_exhausted", "Budget exhausted");
        }

        RequestContext context = RequestContextHolder.get();
        Map<String, Object> body = objectMapper.convertValue(request, Map.class);
        String authUserId = resolveAuthenticatedUserId();
        boolean shouldStream = Boolean.TRUE.equals(stream)
            || (request.getOptions() != null && Boolean.TRUE.equals(request.getOptions().getStream()));

        String conversationId = resolveConversationId(request, context, authUserId);
        body.put("session_id", conversationId);
        enforceAuthenticatedUser(body, authUserId);
        String canonicalKey = canonicalKey(request.getMessage().getContent());
        String queryText = resolveQueryText(request);
        String turnId = resolveTurnId(context);
        recordChatRequestEvent(request, context, conversationId, turnId, canonicalKey, shouldStream, queryText);

        if (shouldStream) {
            SseEmitter emitter = new SseEmitter(0L);
            CompletableFuture.runAsync(() -> streamFromQueryService(emitter, body, context, conversationId, turnId, canonicalKey, queryText));
            return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .body(emitter);
        }

        JsonNode responseNode = queryServiceClient.chat(body, context);
        if (responseNode == null) {
            throw new BadRequestException("chat response is empty");
        }
        BffChatResponse response = objectMapper.convertValue(responseNode, BffChatResponse.class);
        recordChatResponseEvent(response, context, conversationId, turnId, canonicalKey, false, null, queryText);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/feedback")
    public BffAckResponse feedback(@RequestBody(required = false) BffChatFeedbackRequest request) {
        if (request == null || request.getSessionId() == null || request.getSessionId().isBlank()) {
            throw new BadRequestException("session_id is required");
        }
        String rating = request.getRating() == null ? "" : request.getRating().trim().toLowerCase();
        if (!"up".equals(rating) && !"down".equals(rating)) {
            throw new BadRequestException("rating must be one of: up, down");
        }
        RequestContext context = RequestContextHolder.get();
        String authUserId = resolveAuthenticatedUserId();
        String conversationId = normalizeSessionIdForUser(request.getSessionId().trim(), authUserId);
        Map<String, Object> payload = new HashMap<>();
        payload.put("version", request.getVersion());
        payload.put("trace_id", context == null ? null : context.getTraceId());
        payload.put("request_id", context == null ? null : context.getRequestId());
        payload.put("conversation_id", conversationId);
        payload.put("turn_id", request.getMessageId());
        payload.put("canonical_key", null);
        payload.put("used_chunk_ids", List.of());
        payload.put("session_id", conversationId);
        payload.put("message_id", request.getMessageId());
        payload.put("rating", rating);
        payload.put("reason_code", request.getReasonCode());
        payload.put("comment", request.getComment());
        payload.put("flag_hallucination", request.getFlagHallucination());
        payload.put("flag_insufficient", request.getFlagInsufficient());
        payload.put("actor_user_id", authUserId);
        payload.put("auth_mode", authUserId == null ? "anonymous" : "user");
        payload.put("event_time", OffsetDateTime.now(ZoneOffset.UTC).toString());
        String aggregateId = request.getMessageId();
        if (aggregateId == null || aggregateId.isBlank()) {
            aggregateId = conversationId + ":" + (context == null ? "" : context.getRequestId());
        }
        outboxService.record("chat_feedback_v1", "chat_message", aggregateId, payload);
        return ack(context);
    }

    @GetMapping("/recommend/experiment")
    public ResponseEntity<JsonNode> recommendExperimentSnapshot() {
        RequestContext context = RequestContextHolder.get();
        requireAdminContext();
        JsonNode response = queryServiceClient.chatRecommendExperimentSnapshot(context);
        if (response == null) {
            throw new DownstreamException(HttpStatus.BAD_GATEWAY, "query_service_error", "Query service response is empty");
        }
        return ResponseEntity.ok(response);
    }

    @GetMapping("/rollout")
    public ResponseEntity<JsonNode> rolloutSnapshot() {
        RequestContext context = RequestContextHolder.get();
        requireAdminContext();
        JsonNode response = queryServiceClient.chatRolloutSnapshot(context);
        if (response == null) {
            throw new DownstreamException(HttpStatus.BAD_GATEWAY, "query_service_error", "Query service response is empty");
        }
        return ResponseEntity.ok(response);
    }

    @PostMapping("/rollout/reset")
    public ResponseEntity<JsonNode> rolloutReset(
        @RequestBody(required = false) Map<String, Object> request
    ) {
        RequestContext context = RequestContextHolder.get();
        requireAdminContext();
        JsonNode response = queryServiceClient.resetChatRollout(context, request == null ? Map.of() : request);
        if (response == null) {
            throw new DownstreamException(HttpStatus.BAD_GATEWAY, "query_service_error", "Query service response is empty");
        }
        return ResponseEntity.ok(response);
    }

    @PostMapping("/recommend/experiment/reset")
    public ResponseEntity<JsonNode> recommendExperimentReset(
        @RequestBody(required = false) Map<String, Object> request
    ) {
        RequestContext context = RequestContextHolder.get();
        requireAdminContext();
        JsonNode response = queryServiceClient.resetChatRecommendExperiment(context, request == null ? Map.of() : request);
        if (response == null) {
            throw new DownstreamException(HttpStatus.BAD_GATEWAY, "query_service_error", "Query service response is empty");
        }
        return ResponseEntity.ok(response);
    }

    @PostMapping("/recommend/experiment/config")
    public ResponseEntity<JsonNode> recommendExperimentConfig(
        @RequestBody(required = false) Map<String, Object> request
    ) {
        RequestContext context = RequestContextHolder.get();
        requireAdminContext();
        JsonNode response = queryServiceClient.chatRecommendExperimentConfig(context, request == null ? Map.of() : request);
        if (response == null) {
            throw new DownstreamException(HttpStatus.BAD_GATEWAY, "query_service_error", "Query service response is empty");
        }
        return ResponseEntity.ok(response);
    }

    @GetMapping("/session/state")
    public ResponseEntity<JsonNode> sessionState(
        @RequestParam(value = "session_id", required = false) String sessionId
    ) {
        if (sessionId == null || sessionId.isBlank()) {
            throw new BadRequestException("session_id is required");
        }
        RequestContext context = RequestContextHolder.get();
        String authUserId = resolveAuthenticatedUserId();
        String normalizedSessionId = normalizeSessionIdForUser(sessionId.trim(), authUserId);
        JsonNode response = queryServiceClient.chatSessionState(normalizedSessionId, context);
        if (response == null) {
            throw new DownstreamException(HttpStatus.BAD_GATEWAY, "query_service_error", "Query service response is empty");
        }
        return ResponseEntity.ok(response);
    }

    @PostMapping("/session/reset")
    public ResponseEntity<JsonNode> sessionReset(
        @RequestBody(required = false) Map<String, Object> request
    ) {
        if (request == null) {
            throw new BadRequestException("request body is required");
        }
        Object rawSessionId = request.get("session_id");
        String sessionId = rawSessionId instanceof String ? ((String) rawSessionId).trim() : "";
        if (sessionId.isBlank()) {
            throw new BadRequestException("session_id is required");
        }
        RequestContext context = RequestContextHolder.get();
        String authUserId = resolveAuthenticatedUserId();
        String normalizedSessionId = normalizeSessionIdForUser(sessionId, authUserId);
        JsonNode response = queryServiceClient.resetChatSession(normalizedSessionId, context);
        if (response == null) {
            throw new DownstreamException(HttpStatus.BAD_GATEWAY, "query_service_error", "Query service response is empty");
        }
        return ResponseEntity.ok(response);
    }

    private void streamFromQueryService(
        SseEmitter emitter,
        Map<String, Object> body,
        RequestContext context,
        String conversationId,
        String turnId,
        String canonicalKey,
        String queryText
    ) {
        try {
            ChatStreamResult streamResult = queryServiceClient.chatStream(body, context, emitter);
            BffChatResponse response = new BffChatResponse();
            response.setVersion("v1");
            response.setStatus(streamResult.getStatus());
            response.setReasonCode(streamResult.getReasonCode());
            response.setRecoverable(streamResult.getRecoverable());
            response.setNextAction(streamResult.getNextAction());
            response.setRetryAfterMs(streamResult.getRetryAfterMs());
            response.setFallbackCount(streamResult.getFallbackCount());
            response.setEscalated(streamResult.getEscalated());
            response.setSources(List.of());
            response.setCitations(streamResult.getCitations());
            recordChatResponseEvent(response, context, conversationId, turnId, canonicalKey, true, streamResult.getCitations(), queryText);
            emitter.complete();
        } catch (Exception ex) {
            BffChatResponse response = new BffChatResponse();
            response.setVersion("v1");
            response.setStatus("error");
            response.setReasonCode("stream_error");
            response.setRecoverable(Boolean.TRUE);
            response.setNextAction("RETRY");
            response.setRetryAfterMs(3000);
            response.setFallbackCount(null);
            response.setEscalated(Boolean.FALSE);
            response.setSources(List.of());
            response.setCitations(List.of());
            recordChatResponseEvent(response, context, conversationId, turnId, canonicalKey, true, null, queryText);
            try {
                emitter.send(
                    SseEmitter.event()
                        .name("error")
                        .data("{\"code\":\"stream_error\",\"message\":\"chat stream failed\"}", MediaType.TEXT_PLAIN)
                );
            } catch (Exception ignored) {
                // ignore
            }
            emitter.completeWithError(ex);
        }
    }

    private void recordChatRequestEvent(
        BffChatRequest request,
        RequestContext context,
        String conversationId,
        String turnId,
        String canonicalKey,
        boolean stream,
        String queryText
    ) {
        Map<String, Object> payload = new HashMap<>();
        payload.put("version", request.getVersion());
        payload.put("trace_id", context == null ? null : context.getTraceId());
        payload.put("request_id", context == null ? null : context.getRequestId());
        payload.put("conversation_id", conversationId);
        payload.put("turn_id", turnId);
        payload.put("session_id", request.getSessionId());
        payload.put("canonical_key", canonicalKey);
        payload.put("query", request.getMessage() == null ? null : request.getMessage().getContent());
        payload.put("risk_band_hint", computeRiskBandHint(queryText));
        payload.put("stream", stream);
        payload.put("top_k", request.getOptions() == null ? null : request.getOptions().getTopK());
        payload.put("event_time", OffsetDateTime.now(ZoneOffset.UTC).toString());
        outboxService.record("chat_request_v1", "chat_session", buildTurnAggregateId(conversationId, turnId, "request"), payload);
    }

    private void recordChatResponseEvent(
        BffChatResponse response,
        RequestContext context,
        String conversationId,
        String turnId,
        String canonicalKey,
        boolean stream,
        List<String> streamChunkIds,
        String queryText
    ) {
        Map<String, Object> payload = new HashMap<>();
        payload.put("version", response == null ? "v1" : response.getVersion());
        payload.put("trace_id", context == null ? null : context.getTraceId());
        payload.put("request_id", context == null ? null : context.getRequestId());
        payload.put("conversation_id", conversationId);
        payload.put("turn_id", turnId);
        payload.put("canonical_key", canonicalKey);
        payload.put("status", response == null ? "error" : response.getStatus());
        payload.put("reason_code", response == null ? null : response.getReasonCode());
        payload.put("recoverable", response == null ? null : response.getRecoverable());
        payload.put("next_action", response == null ? null : response.getNextAction());
        payload.put("retry_after_ms", response == null ? null : response.getRetryAfterMs());
        payload.put("fallback_count", response == null ? null : response.getFallbackCount());
        payload.put("escalated", response == null ? null : response.getEscalated());
        payload.put("stream", stream);
        payload.put("citations", response == null ? List.of() : response.getCitations());
        payload.put("risk_band", computeRiskBand(queryText, response == null ? "error" : response.getStatus(), response == null ? List.of() : response.getCitations()));
        payload.put("used_chunk_ids", extractChunkIds(response == null ? null : response.getSources(), streamChunkIds));
        payload.put("source_count", response == null || response.getSources() == null ? 0 : response.getSources().size());
        payload.put("event_time", OffsetDateTime.now(ZoneOffset.UTC).toString());
        outboxService.record("chat_response_v1", "chat_session", buildTurnAggregateId(conversationId, turnId, "response"), payload);
    }

    private List<String> extractChunkIds(List<BffChatSource> sources, List<String> fallbackChunkIds) {
        List<String> chunkIds = new ArrayList<>();
        if (sources != null) {
            for (BffChatSource source : sources) {
                if (source == null || source.getChunkId() == null || source.getChunkId().isBlank()) {
                    continue;
                }
                if (!chunkIds.contains(source.getChunkId())) {
                    chunkIds.add(source.getChunkId());
                }
            }
        }
        if (!chunkIds.isEmpty()) {
            return chunkIds;
        }
        if (fallbackChunkIds == null || fallbackChunkIds.isEmpty()) {
            return List.of();
        }
        for (String fallbackChunkId : fallbackChunkIds) {
            if (fallbackChunkId == null || fallbackChunkId.isBlank()) {
                continue;
            }
            if (!chunkIds.contains(fallbackChunkId)) {
                chunkIds.add(fallbackChunkId);
            }
        }
        return chunkIds;
    }

    private String resolveConversationId(BffChatRequest request, RequestContext context, String authUserId) {
        String requestedSessionId = null;
        if (request != null && request.getSessionId() != null && !request.getSessionId().isBlank()) {
            requestedSessionId = request.getSessionId().trim();
        }
        if (authUserId != null) {
            if (requestedSessionId == null || requestedSessionId.isBlank()) {
                return "u:" + authUserId + ":default";
            }
            return normalizeSessionIdForUser(requestedSessionId, authUserId);
        }
        if (requestedSessionId != null && !requestedSessionId.isBlank()) {
            return requestedSessionId;
        }
        String requestId = context == null ? null : context.getRequestId();
        if (requestId != null && !requestId.isBlank()) {
            return "conv:" + requestId;
        }
        return "conv:unknown";
    }

    @SuppressWarnings("unchecked")
    private void enforceAuthenticatedUser(Map<String, Object> body, String authUserId) {
        if (authUserId == null || authUserId.isBlank()) {
            return;
        }
        Object rawClient = body.get("client");
        Map<String, Object> clientPayload = new HashMap<>();
        if (rawClient instanceof Map<?, ?> rawMap) {
            for (Map.Entry<?, ?> entry : rawMap.entrySet()) {
                if (entry.getKey() != null) {
                    clientPayload.put(String.valueOf(entry.getKey()), entry.getValue());
                }
            }
        }
        clientPayload.put("user_id", authUserId);
        body.put("client", clientPayload);
    }

    private String resolveAuthenticatedUserId() {
        AuthContext authContext = AuthContextHolder.get();
        if (authContext == null || authContext.getUserId() == null) {
            return null;
        }
        String normalized = authContext.getUserId().trim();
        if (normalized.isBlank()) {
            return null;
        }
        return normalized;
    }

    private void requireAdminContext() {
        AuthContext authContext = AuthContextHolder.get();
        if (authContext == null || !authContext.isAdmin()) {
            throw new DownstreamException(HttpStatus.FORBIDDEN, "forbidden", "admin authentication required");
        }
    }

    private String normalizeSessionIdForUser(String sessionId, String authUserId) {
        if (sessionId == null) {
            return "";
        }
        String normalizedSessionId = sessionId.trim();
        if (normalizedSessionId.isBlank()) {
            return "";
        }
        if (authUserId == null || authUserId.isBlank()) {
            return normalizedSessionId;
        }
        String ownerUserId = extractSessionOwnerUserId(normalizedSessionId);
        if (ownerUserId == null) {
            return "u:" + authUserId + ":" + normalizedSessionId;
        }
        if (!authUserId.equals(ownerUserId)) {
            throw new DownstreamException(HttpStatus.FORBIDDEN, "forbidden", "session_id is not allowed for current user");
        }
        return normalizedSessionId;
    }

    private String extractSessionOwnerUserId(String sessionId) {
        Matcher matcher = USER_SESSION_PATTERN.matcher(sessionId);
        if (!matcher.find()) {
            return null;
        }
        String candidate = matcher.group(1);
        if (candidate == null || candidate.isBlank()) {
            return null;
        }
        return candidate;
    }

    private String resolveTurnId(RequestContext context) {
        if (context != null && context.getRequestId() != null && !context.getRequestId().isBlank()) {
            return context.getRequestId().trim();
        }
        return "turn:" + UUID.randomUUID();
    }

    private String buildTurnAggregateId(String conversationId, String turnId, String eventKind) {
        String safeConversationId = (conversationId == null || conversationId.isBlank()) ? "conv:unknown" : conversationId.trim();
        String safeTurnId = (turnId == null || turnId.isBlank()) ? "turn:unknown" : turnId.trim();
        String safeKind = (eventKind == null || eventKind.isBlank()) ? "event" : eventKind.trim();
        return safeConversationId + ":" + safeTurnId + ":" + safeKind;
    }

    private String canonicalKey(String message) {
        String normalized = message == null ? "" : message.trim().toLowerCase().replaceAll("\\s+", " ");
        if (normalized.isBlank()) {
            return "ck:empty";
        }
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hashed = digest.digest(normalized.getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder();
            for (int i = 0; i < 8; i++) {
                builder.append(String.format("%02x", hashed[i]));
            }
            return "ck:" + builder;
        } catch (NoSuchAlgorithmException ex) {
            return "ck:" + Integer.toHexString(normalized.hashCode());
        }
    }

    private String resolveQueryText(BffChatRequest request) {
        if (request == null || request.getMessage() == null || request.getMessage().getContent() == null) {
            return "";
        }
        return request.getMessage().getContent();
    }

    private String computeRiskBandHint(String queryText) {
        return isHighRiskQuery(queryText) ? "R2" : "R0";
    }

    private String computeRiskBand(String queryText, String status, List<String> citations) {
        String normalizedStatus = status == null ? "" : status.trim().toLowerCase();
        int citationCount = 0;
        if (citations != null) {
            for (String citation : citations) {
                if (citation != null && !citation.isBlank()) {
                    citationCount += 1;
                }
            }
        }
        boolean highRisk = isHighRiskQuery(queryText);
        if ("error".equals(normalizedStatus) || "insufficient_evidence".equals(normalizedStatus)) {
            return "R3";
        }
        if (highRisk && citationCount == 0) {
            return "R3";
        }
        if (highRisk) {
            return "R2";
        }
        if (citationCount == 0) {
            return "R1";
        }
        return "R0";
    }

    private boolean isHighRiskQuery(String queryText) {
        if (queryText == null || queryText.isBlank()) {
            return false;
        }
        String normalized = queryText.toLowerCase();
        for (String keyword : HIGH_RISK_KEYWORDS) {
            if (normalized.contains(keyword)) {
                return true;
            }
        }
        return false;
    }

    private BffAckResponse ack(RequestContext context) {
        BffAckResponse response = new BffAckResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setStatus("ok");
        return response;
    }
}
