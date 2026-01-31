package com.bsl.bff.api;

import com.bsl.bff.api.dto.BffAckResponse;
import com.bsl.bff.api.dto.BffChatFeedbackRequest;
import com.bsl.bff.api.dto.BffChatRequest;
import com.bsl.bff.api.dto.BffChatResponse;
import com.bsl.bff.client.QueryServiceClient;
import com.bsl.bff.common.BadRequestException;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.outbox.OutboxService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.HashMap;
import java.util.Map;
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
        RequestContext context = RequestContextHolder.get();
        Map<String, Object> body = objectMapper.convertValue(request, Map.class);
        JsonNode responseNode = queryServiceClient.chat(body, context);
        if (responseNode == null) {
            throw new BadRequestException("chat response is empty");
        }
        BffChatResponse response = objectMapper.convertValue(responseNode, BffChatResponse.class);
        boolean shouldStream = Boolean.TRUE.equals(stream) || (request.getOptions() != null && Boolean.TRUE.equals(request.getOptions().getStream()));
        if (!shouldStream) {
            return ResponseEntity.ok(response);
        }
        SseEmitter emitter = new SseEmitter(0L);
        CompletableFuture.runAsync(() -> streamResponse(emitter, response));
        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .body(emitter);
    }

    @PostMapping("/feedback")
    public BffAckResponse feedback(@RequestBody(required = false) BffChatFeedbackRequest request) {
        if (request == null || request.getSessionId() == null || request.getSessionId().isBlank()) {
            throw new BadRequestException("session_id is required");
        }
        RequestContext context = RequestContextHolder.get();
        Map<String, Object> payload = new HashMap<>();
        payload.put("version", request.getVersion());
        payload.put("trace_id", context == null ? null : context.getTraceId());
        payload.put("request_id", context == null ? null : context.getRequestId());
        payload.put("session_id", request.getSessionId());
        payload.put("message_id", request.getMessageId());
        payload.put("rating", request.getRating());
        payload.put("reason_code", request.getReasonCode());
        payload.put("comment", request.getComment());
        payload.put("flag_hallucination", request.getFlagHallucination());
        payload.put("flag_insufficient", request.getFlagInsufficient());
        String aggregateId = request.getMessageId();
        if (aggregateId == null || aggregateId.isBlank()) {
            aggregateId = request.getSessionId() + ":" + (context == null ? \"\" : context.getRequestId());
        }
        outboxService.record("chat_feedback_v1", "chat_message", aggregateId, payload);
        return ack(context);
    }

    private void streamResponse(SseEmitter emitter, BffChatResponse response) {
        try {
            String meta = objectMapper.writeValueAsString(response);
            emitter.send(SseEmitter.event().name("meta").data(meta, MediaType.APPLICATION_JSON));
            String content = response.getAnswer() == null ? "" : response.getAnswer().getContent();
            for (String token : content.split("\\s+")) {
                if (!token.isBlank()) {
                    emitter.send(SseEmitter.event().name("token").data(token + " ", MediaType.TEXT_PLAIN));
                }
            }
            emitter.send(SseEmitter.event().name("done").data("[DONE]", MediaType.TEXT_PLAIN));
            emitter.complete();
        } catch (Exception ex) {
            try {
                emitter.send(SseEmitter.event().name("error").data("stream_error", MediaType.TEXT_PLAIN));
            } catch (Exception ignored) {
                // ignore
            }
            emitter.completeWithError(ex);
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
