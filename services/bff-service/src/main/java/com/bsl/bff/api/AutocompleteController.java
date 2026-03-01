package com.bsl.bff.api;

import com.bsl.bff.api.dto.BffAckResponse;
import com.bsl.bff.api.dto.BffAutocompleteResponse;
import com.bsl.bff.api.dto.BffAutocompleteSelectRequest;
import com.bsl.bff.client.AutocompleteServiceClient;
import com.bsl.bff.client.dto.AutocompleteServiceResponse;
import com.bsl.bff.common.BadRequestException;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.outbox.OutboxService;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AutocompleteController {
    private static final int DEFAULT_SIZE = 10;

    private final AutocompleteServiceClient autocompleteServiceClient;
    private final OutboxService outboxService;

    public AutocompleteController(AutocompleteServiceClient autocompleteServiceClient, OutboxService outboxService) {
        this.autocompleteServiceClient = autocompleteServiceClient;
        this.outboxService = outboxService;
    }

    @GetMapping({"/autocomplete", "/v1/autocomplete"})
    public BffAutocompleteResponse autocomplete(
        @RequestParam(value = "q", required = false) String query,
        @RequestParam(value = "size", required = false) Integer size
    ) {
        RequestContext context = RequestContextHolder.get();
        String trimmed = query == null ? "" : query.trim();
        int resolvedSize = size == null ? DEFAULT_SIZE : Math.max(size, 1);
        long started = System.nanoTime();

        BffAutocompleteResponse response = new BffAutocompleteResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());

        AutocompleteServiceResponse downstream = autocompleteServiceClient.autocomplete(trimmed, resolvedSize, context);
        response.setTookMs(downstream != null && downstream.getTookMs() > 0
            ? downstream.getTookMs()
            : (System.nanoTime() - started) / 1_000_000L);

        List<BffAutocompleteResponse.Suggestion> suggestions = new ArrayList<>();
        if (downstream != null && downstream.getSuggestions() != null) {
            for (AutocompleteServiceResponse.Suggestion suggestion : downstream.getSuggestions()) {
                if (suggestion == null) {
                    continue;
                }
                BffAutocompleteResponse.Suggestion mapped = new BffAutocompleteResponse.Suggestion();
                mapped.setText(suggestion.getText());
                mapped.setScore(suggestion.getScore());
                mapped.setSource(suggestion.getSource());
                mapped.setSuggestId(suggestion.getSuggestId());
                mapped.setType(suggestion.getType());
                mapped.setTargetId(suggestion.getTargetId());
                mapped.setTargetDocId(suggestion.getTargetDocId());
                suggestions.add(mapped);
            }
        }
        response.setSuggestions(suggestions);

        recordImpression(context, trimmed, resolvedSize, suggestions);

        return response;
    }

    @PostMapping({"/autocomplete/select", "/v1/autocomplete/select"})
    public BffAckResponse autocompleteSelect(@RequestBody(required = false) BffAutocompleteSelectRequest request) {
        RequestContext context = RequestContextHolder.get();
        if (request == null || request.getText() == null || request.getText().isBlank()) {
            throw new BadRequestException("text is required");
        }
        String text = request.getText().trim();
        if (text.isEmpty()) {
            throw new BadRequestException("text is required");
        }
        Map<String, Object> payload = new HashMap<>();
        if (request.getQ() != null && !request.getQ().isBlank()) {
            payload.put("q", request.getQ().trim());
        }
        payload.put("text", text);
        if (request.getSuggestId() != null && !request.getSuggestId().isBlank()) {
            payload.put("suggest_id", request.getSuggestId());
        }
        if (request.getType() != null && !request.getType().isBlank()) {
            payload.put("type", request.getType());
        }
        if (request.getPosition() != null && request.getPosition() >= 0) {
            payload.put("position", request.getPosition());
        }
        if (request.getSource() != null && !request.getSource().isBlank()) {
            payload.put("source", request.getSource());
        }
        if (request.getTargetId() != null && !request.getTargetId().isBlank()) {
            payload.put("target_id", request.getTargetId());
        }
        if (request.getTargetDocId() != null && !request.getTargetDocId().isBlank()) {
            payload.put("target_doc_id", request.getTargetDocId());
        }
        recordSelect(context, payload);

        BffAckResponse response = new BffAckResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setStatus("ok");
        return response;
    }

    private void recordImpression(
        RequestContext context,
        String query,
        int size,
        List<BffAutocompleteResponse.Suggestion> suggestions
    ) {
        if (context == null) {
            return;
        }
        List<Map<String, Object>> impressionSuggestions = new ArrayList<>();
        int position = 1;
        for (BffAutocompleteResponse.Suggestion suggestion : suggestions) {
            if (suggestion == null || suggestion.getText() == null) {
                continue;
            }
            Map<String, Object> entry = new HashMap<>();
            entry.put("text", suggestion.getText());
            entry.put("position", position++);
            if (suggestion.getSuggestId() != null && !suggestion.getSuggestId().isBlank()) {
                entry.put("suggest_id", suggestion.getSuggestId());
            }
            if (suggestion.getType() != null && !suggestion.getType().isBlank()) {
                entry.put("type", suggestion.getType());
            }
            if (suggestion.getSource() != null && !suggestion.getSource().isBlank()) {
                entry.put("source", suggestion.getSource());
            }
            if (suggestion.getTargetId() != null && !suggestion.getTargetId().isBlank()) {
                entry.put("target_id", suggestion.getTargetId());
            }
            if (suggestion.getTargetDocId() != null && !suggestion.getTargetDocId().isBlank()) {
                entry.put("target_doc_id", suggestion.getTargetDocId());
            }
            impressionSuggestions.add(entry);
        }
        Map<String, Object> payload = new HashMap<>();
        payload.put("q", query);
        payload.put("size", size);
        payload.put("count", impressionSuggestions.size());
        payload.put("suggestions", impressionSuggestions);
        recordOutbox("ac_impression", "autocomplete", context, payload, context.getRequestId());
    }

    private void recordSelect(RequestContext context, Map<String, Object> payload) {
        if (context == null) {
            return;
        }
        String aggregateId = context.getRequestId();
        Object suggestId = payload.get("suggest_id");
        Object text = payload.get("text");
        Object position = payload.get("position");
        if (suggestId != null) {
            aggregateId = context.getRequestId() + ":" + suggestId + ":" + (position == null ? "0" : position);
        } else if (text != null) {
            aggregateId = context.getRequestId() + ":" + text.toString();
        }
        recordOutbox("ac_select", "autocomplete", context, payload, aggregateId);
    }

    private void recordOutbox(
        String eventType,
        String aggregateType,
        RequestContext context,
        Map<String, Object> payload,
        String aggregateId
    ) {
        if (context == null) {
            return;
        }
        Map<String, Object> enriched = new HashMap<>(payload);
        enriched.put("request_id", context.getRequestId());
        enriched.put("trace_id", context.getTraceId());
        outboxService.record(eventType, aggregateType, aggregateId, enriched);
    }
}
