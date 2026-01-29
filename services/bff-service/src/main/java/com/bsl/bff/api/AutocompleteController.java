package com.bsl.bff.api;

import com.bsl.bff.api.dto.BffAutocompleteResponse;
import com.bsl.bff.client.AutocompleteServiceClient;
import com.bsl.bff.client.dto.AutocompleteServiceResponse;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.outbox.OutboxService;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
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

        if (trimmed.isEmpty()) {
            response.setTookMs((System.nanoTime() - started) / 1_000_000L);
            response.setSuggestions(List.of());
            return response;
        }

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
                suggestions.add(mapped);
            }
        }
        response.setSuggestions(suggestions);

        recordOutbox("autocomplete_request", "autocomplete", context, Map.of(
            "q", trimmed,
            "size", resolvedSize
        ));

        return response;
    }

    private void recordOutbox(String eventType, String aggregateType, RequestContext context, Map<String, Object> payload) {
        if (context == null) {
            return;
        }
        Map<String, Object> enriched = new HashMap<>(payload);
        enriched.put("request_id", context.getRequestId());
        enriched.put("trace_id", context.getTraceId());
        outboxService.record(eventType, aggregateType, context.getRequestId(), enriched);
    }
}
