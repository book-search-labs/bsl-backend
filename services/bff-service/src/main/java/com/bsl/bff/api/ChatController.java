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
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/chat")
public class ChatController {
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
        boolean shouldStream = Boolean.TRUE.equals(stream)
            || (request.getOptions() != null && Boolean.TRUE.equals(request.getOptions().getStream()));

        String conversationId = resolveConversationId(request, context);
        String canonicalKey = canonicalKey(request.getMessage().getContent());
        String turnId = resolveTurnId(context);
        recordChatRequestEvent(request, context, conversationId, turnId, canonicalKey, shouldStream);

        if (shouldStream) {
            SseEmitter emitter = new SseEmitter(0L);
            CompletableFuture.runAsync(() -> streamFromQueryService(emitter, body, context, conversationId, turnId, canonicalKey));
            return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .body(emitter);
        }

        JsonNode responseNode = queryServiceClient.chat(body, context);
        if (responseNode == null) {
            throw new BadRequestException("chat response is empty");
        }
        BffChatResponse response = objectMapper.convertValue(responseNode, BffChatResponse.class);
        recordChatResponseEvent(response, context, conversationId, turnId, canonicalKey, false, null);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/feedback")
    public BffAckResponse feedback(@RequestBody(required = false) BffChatFeedbackRequest request) {
        if (request == null || request.getSessionId() == null || request.getSessionId().isBlank()) {
            throw new BadRequestException("session_id is required");
        }
        RequestContext context = RequestContextHolder.get();
        String conversationId = request.getSessionId();
        Map<String, Object> payload = new HashMap<>();
        payload.put("version", request.getVersion());
        payload.put("trace_id", context == null ? null : context.getTraceId());
        payload.put("request_id", context == null ? null : context.getRequestId());
        payload.put("conversation_id", conversationId);
        payload.put("turn_id", request.getMessageId());
        payload.put("canonical_key", null);
        payload.put("used_chunk_ids", List.of());
        payload.put("session_id", request.getSessionId());
        payload.put("message_id", request.getMessageId());
        payload.put("rating", request.getRating());
        payload.put("reason_code", request.getReasonCode());
        payload.put("comment", request.getComment());
        payload.put("flag_hallucination", request.getFlagHallucination());
        payload.put("flag_insufficient", request.getFlagInsufficient());
        payload.put("event_time", OffsetDateTime.now(ZoneOffset.UTC).toString());
        String aggregateId = request.getMessageId();
        if (aggregateId == null || aggregateId.isBlank()) {
            aggregateId = conversationId + ":" + (context == null ? "" : context.getRequestId());
        }
        outboxService.record("chat_feedback_v1", "chat_message", aggregateId, payload);
        return ack(context);
    }

    private void streamFromQueryService(
        SseEmitter emitter,
        Map<String, Object> body,
        RequestContext context,
        String conversationId,
        String turnId,
        String canonicalKey
    ) {
        try {
            ChatStreamResult streamResult = queryServiceClient.chatStream(body, context, emitter);
            BffChatResponse response = new BffChatResponse();
            response.setVersion("v1");
            response.setStatus(streamResult.getStatus());
            response.setSources(List.of());
            response.setCitations(streamResult.getCitations());
            recordChatResponseEvent(response, context, conversationId, turnId, canonicalKey, true, streamResult.getCitations());
            emitter.complete();
        } catch (Exception ex) {
            BffChatResponse response = new BffChatResponse();
            response.setVersion("v1");
            response.setStatus("error");
            response.setSources(List.of());
            response.setCitations(List.of());
            recordChatResponseEvent(response, context, conversationId, turnId, canonicalKey, true, null);
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
        boolean stream
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
        List<String> streamChunkIds
    ) {
        Map<String, Object> payload = new HashMap<>();
        payload.put("version", response == null ? "v1" : response.getVersion());
        payload.put("trace_id", context == null ? null : context.getTraceId());
        payload.put("request_id", context == null ? null : context.getRequestId());
        payload.put("conversation_id", conversationId);
        payload.put("turn_id", turnId);
        payload.put("canonical_key", canonicalKey);
        payload.put("status", response == null ? "error" : response.getStatus());
        payload.put("stream", stream);
        payload.put("citations", response == null ? List.of() : response.getCitations());
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

    private String resolveConversationId(BffChatRequest request, RequestContext context) {
        if (request != null && request.getSessionId() != null && !request.getSessionId().isBlank()) {
            return request.getSessionId().trim();
        }
        String requestId = context == null ? null : context.getRequestId();
        if (requestId != null && !requestId.isBlank()) {
            return "conv:" + requestId;
        }
        return "conv:unknown";
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

    private BffAckResponse ack(RequestContext context) {
        BffAckResponse response = new BffAckResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setStatus("ok");
        return response;
    }
}
