package com.bsl.bff.ops;

import com.bsl.bff.client.AutocompleteAdminClient;
import com.bsl.bff.client.dto.AutocompleteAdminServiceResponse;
import com.bsl.bff.client.dto.AutocompleteAdminServiceUpdateResponse;
import com.bsl.bff.common.BadRequestException;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.ops.dto.AutocompleteSuggestionDto;
import com.bsl.bff.ops.dto.AutocompleteSuggestionUpdateRequest;
import com.bsl.bff.ops.dto.AutocompleteSuggestionUpdateResponse;
import com.bsl.bff.ops.dto.AutocompleteSuggestionsResponse;
import com.bsl.bff.ops.dto.AutocompleteTrendDto;
import com.bsl.bff.ops.dto.AutocompleteTrendsResponse;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/admin/ops/autocomplete")
public class AutocompleteOpsController {
    private static final int DEFAULT_LIMIT = 50;
    private static final int MAX_LIMIT = 500;

    private final AutocompleteAdminClient autocompleteAdminClient;
    private final AutocompleteOpsRepository repository;

    public AutocompleteOpsController(
        AutocompleteAdminClient autocompleteAdminClient,
        AutocompleteOpsRepository repository
    ) {
        this.autocompleteAdminClient = autocompleteAdminClient;
        this.repository = repository;
    }

    @GetMapping("/suggestions")
    public AutocompleteSuggestionsResponse suggestions(
        @RequestParam(value = "q", required = false) String query,
        @RequestParam(value = "size", required = false) Integer size,
        @RequestParam(value = "include_blocked", required = false) Boolean includeBlocked
    ) {
        RequestContext context = RequestContextHolder.get();
        AutocompleteAdminServiceResponse downstream = autocompleteAdminClient.searchSuggestions(
            query,
            size,
            includeBlocked,
            context
        );
        AutocompleteSuggestionsResponse response = new AutocompleteSuggestionsResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setTookMs(downstream == null ? 0 : downstream.getTookMs());
        response.setSuggestions(downstream == null ? List.of() : downstream.getSuggestions());
        return response;
    }

    @PostMapping("/suggestions/{id}")
    public AutocompleteSuggestionUpdateResponse updateSuggestion(
        @PathVariable("id") String suggestId,
        @RequestBody(required = false) AutocompleteSuggestionUpdateRequest request
    ) {
        if (suggestId == null || suggestId.isBlank()) {
            throw new BadRequestException("suggest_id is required");
        }
        if (request == null || (request.getWeight() == null && request.getBlocked() == null)) {
            throw new BadRequestException("weight or is_blocked is required");
        }
        RequestContext context = RequestContextHolder.get();
        AutocompleteAdminServiceUpdateResponse downstream = autocompleteAdminClient.updateSuggestion(
            suggestId,
            request,
            context
        );
        AutocompleteSuggestionUpdateResponse response = new AutocompleteSuggestionUpdateResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setSuggestion(downstream == null ? null : downstream.getSuggestion());
        return response;
    }

    @GetMapping("/trends")
    public AutocompleteTrendsResponse trends(
        @RequestParam(value = "metric", required = false) String metric,
        @RequestParam(value = "limit", required = false) Integer limit
    ) {
        int resolved = clampLimit(limit);
        List<AutocompleteTrendDto> items = repository.fetchTrends(metric, resolved);
        RequestContext context = RequestContextHolder.get();
        AutocompleteTrendsResponse response = new AutocompleteTrendsResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setMetric(metric == null ? "ctr" : metric);
        response.setItems(items);
        response.setCount(items == null ? 0 : items.size());
        return response;
    }

    private int clampLimit(Integer limit) {
        int value = limit == null ? DEFAULT_LIMIT : limit;
        if (value < 1) {
            value = DEFAULT_LIMIT;
        }
        return Math.min(value, MAX_LIMIT);
    }
}
