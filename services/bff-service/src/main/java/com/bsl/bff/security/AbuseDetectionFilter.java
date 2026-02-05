package com.bsl.bff.security;

import com.bsl.bff.common.ErrorResponse;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.HashSet;
import java.util.Set;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingResponseWrapper;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 25)
public class AbuseDetectionFilter extends OncePerRequestFilter {
    private final AbuseDetectionService service;
    private final AbuseDetectionProperties properties;
    private final ObjectMapper objectMapper;

    public AbuseDetectionFilter(
        AbuseDetectionService service,
        AbuseDetectionProperties properties,
        ObjectMapper objectMapper
    ) {
        this.service = service;
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        if (service == null || !service.isEnabled()) {
            filterChain.doFilter(request, response);
            return;
        }

        String identity = resolveIdentity(request);
        if (service.isBlocked(identity)) {
            writeBlocked(response);
            return;
        }

        ContentCachingResponseWrapper wrapped = new ContentCachingResponseWrapper(response);
        try {
            filterChain.doFilter(request, wrapped);
        } finally {
            int status = wrapped.getStatus();
            if (isErrorStatus(status)) {
                service.recordError(identity);
            }
            wrapped.copyBodyToResponse();
        }
    }

    private boolean isErrorStatus(int status) {
        if (properties == null || properties.getErrorStatuses() == null) {
            return false;
        }
        Set<Integer> statuses = new HashSet<>(properties.getErrorStatuses());
        return statuses.contains(status);
    }

    private String resolveIdentity(HttpServletRequest request) {
        AuthContext authContext = AuthContextHolder.get();
        if (authContext != null) {
            if (authContext.isAdmin()) {
                return "admin:" + authContext.getAdminId();
            }
            if (authContext.getUserId() != null && !authContext.getUserId().isBlank()) {
                return "user:" + authContext.getUserId();
            }
        }
        String forwarded = request.getHeader("x-forwarded-for");
        if (forwarded != null && !forwarded.isBlank()) {
            return "ip:" + forwarded.split(",")[0].trim();
        }
        return "ip:" + request.getRemoteAddr();
    }

    private void writeBlocked(HttpServletResponse response) throws IOException {
        response.setStatus(429);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        RequestContext context = RequestContextHolder.get();
        ErrorResponse payload = new ErrorResponse(
            "abuse_blocked",
            "Request blocked due to abuse pattern",
            context == null ? null : context.getTraceId(),
            context == null ? null : context.getRequestId()
        );
        objectMapper.writeValue(response.getWriter(), payload);
    }
}
