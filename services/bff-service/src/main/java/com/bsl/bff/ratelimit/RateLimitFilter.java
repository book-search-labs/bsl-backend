package com.bsl.bff.ratelimit;

import com.bsl.bff.common.ErrorResponse;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.security.AuthContext;
import com.bsl.bff.security.AuthContextHolder;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
public class RateLimitFilter extends OncePerRequestFilter {
    private final RateLimitService rateLimitService;
    private final ObjectMapper objectMapper;

    public RateLimitFilter(RateLimitService rateLimitService, ObjectMapper objectMapper) {
        this.rateLimitService = rateLimitService;
        this.objectMapper = objectMapper;
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        RateLimitProperties props = rateLimitService.getProperties();
        if (!props.isEnabled()) {
            filterChain.doFilter(request, response);
            return;
        }

        String group = resolveGroup(request.getRequestURI());
        int limit = resolveLimit(props, group);
        if (limit <= 0) {
            filterChain.doFilter(request, response);
            return;
        }

        String identity = resolveIdentity(request);
        String key = group + ":" + identity;
        if (!rateLimitService.allow(key, limit)) {
            response.setStatus(429);
            response.setHeader("Retry-After", String.valueOf(props.getWindowSeconds()));
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            RequestContext context = RequestContextHolder.get();
            ErrorResponse payload = new ErrorResponse(
                "rate_limit_exceeded",
                "Too many requests",
                context == null ? null : context.getTraceId(),
                context == null ? null : context.getRequestId()
            );
            objectMapper.writeValue(response.getWriter(), payload);
            return;
        }

        filterChain.doFilter(request, response);
    }

    private String resolveGroup(String path) {
        if (path == null) {
            return "default";
        }
        if (path.startsWith("/search")) {
            return "search";
        }
        if (path.startsWith("/autocomplete")) {
            return "autocomplete";
        }
        if (path.startsWith("/admin")) {
            return "admin";
        }
        return "default";
    }

    private int resolveLimit(RateLimitProperties props, String group) {
        return switch (group) {
            case "search" -> props.getSearchPerMinute();
            case "autocomplete" -> props.getAutocompletePerMinute();
            case "admin" -> props.getAdminPerMinute();
            default -> props.getDefaultPerMinute();
        };
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
}
