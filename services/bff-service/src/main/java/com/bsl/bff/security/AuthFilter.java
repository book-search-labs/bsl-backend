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
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class AuthFilter extends OncePerRequestFilter {
    private final AuthProperties properties;
    private final ObjectMapper objectMapper;

    public AuthFilter(AuthProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        if (!properties.isEnabled()) {
            filterChain.doFilter(request, response);
            return;
        }

        try {
            AuthContext context = resolveAuthContext(request);
            AuthContextHolder.set(context);

            if (isAdminPath(request) && !context.isAdmin()) {
                writeError(response, HttpServletResponse.SC_UNAUTHORIZED, "unauthorized", "Admin auth required");
                return;
            }

            filterChain.doFilter(request, response);
        } finally {
            AuthContextHolder.clear();
        }
    }

    private AuthContext resolveAuthContext(HttpServletRequest request) {
        if (properties.isBypass()) {
            return new AuthContext("dev-user", "dev-admin");
        }
        String adminId = request.getHeader(properties.getAdminHeader());
        String userId = request.getHeader(properties.getUserHeader());
        String authHeader = request.getHeader("Authorization");
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            String token = authHeader.substring("Bearer ".length()).trim();
            if (token.startsWith("admin:")) {
                adminId = token.substring("admin:".length());
            } else if (token.startsWith("user:")) {
                userId = token.substring("user:".length());
            }
        }
        if (adminId != null && adminId.isBlank()) {
            adminId = null;
        }
        if (userId != null && userId.isBlank()) {
            userId = null;
        }
        return new AuthContext(userId, adminId);
    }

    private boolean isAdminPath(HttpServletRequest request) {
        String path = request.getRequestURI();
        return path != null && path.startsWith("/admin");
    }

    private void writeError(HttpServletResponse response, int status, String code, String message) throws IOException {
        RequestContext context = RequestContextHolder.get();
        ErrorResponse payload = new ErrorResponse(
            code,
            message,
            context == null ? null : context.getTraceId(),
            context == null ? null : context.getRequestId()
        );
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        objectMapper.writeValue(response.getWriter(), payload);
    }
}
