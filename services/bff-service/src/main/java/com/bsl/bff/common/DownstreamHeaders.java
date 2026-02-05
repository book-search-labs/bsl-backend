package com.bsl.bff.common;

import org.springframework.http.HttpHeaders;
import com.bsl.bff.budget.BudgetContext;
import com.bsl.bff.budget.BudgetContextHolder;

public final class DownstreamHeaders {
    private DownstreamHeaders() {
    }

    public static HttpHeaders from(RequestContext context) {
        HttpHeaders headers = new HttpHeaders();
        if (context == null) {
            return headers;
        }
        if (context.getRequestId() != null) {
            headers.add("x-request-id", context.getRequestId());
        }
        if (context.getTraceId() != null) {
            headers.add("x-trace-id", context.getTraceId());
        }
        if (context.getTraceparent() != null && !context.getTraceparent().isBlank()) {
            headers.add("traceparent", context.getTraceparent());
        }
        BudgetContext budget = BudgetContextHolder.get();
        if (budget != null) {
            headers.add("x-budget-ms", String.valueOf(budget.remainingMs()));
        }
        return headers;
    }
}
