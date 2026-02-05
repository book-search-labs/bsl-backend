package com.bsl.bff.common;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class BffRequestContextFilter extends OncePerRequestFilter {
    private static final Logger logger = LoggerFactory.getLogger(BffRequestContextFilter.class);

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        String requestId = IdGenerator.resolveRequestId(request.getHeader("x-request-id"));
        String traceparent = request.getHeader("traceparent");
        String traceId = IdGenerator.resolveTraceId(request.getHeader("x-trace-id"), traceparent);
        String resolvedTraceparent = IdGenerator.resolveTraceparent(traceparent, traceId);
        long startedAt = System.nanoTime();

        RequestContext context = new RequestContext(requestId, traceId, resolvedTraceparent, startedAt);
        RequestContextHolder.set(context);
        response.setHeader("x-request-id", requestId);
        response.setHeader("x-trace-id", traceId);
        if (resolvedTraceparent != null && !resolvedTraceparent.isBlank()) {
            response.setHeader("traceparent", resolvedTraceparent);
        }

        try {
            filterChain.doFilter(request, response);
        } finally {
            long latencyMs = (System.nanoTime() - startedAt) / 1_000_000L;
            logger.info(
                "request_id={} trace_id={} method={} path={} status={} latency_ms={}",
                requestId,
                traceId,
                request.getMethod(),
                request.getRequestURI(),
                response.getStatus(),
                latencyMs
            );
            RequestContextHolder.clear();
        }
    }
}
