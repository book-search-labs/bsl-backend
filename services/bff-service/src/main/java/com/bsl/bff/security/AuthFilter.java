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
    private final AuthSessionService authSessionService;
    private final ObjectMapper objectMapper;

    public AuthFilter(AuthProperties properties, AuthSessionService authSessionService, ObjectMapper objectMapper) {
        this.properties = properties;
        this.authSessionService = authSessionService;
        this.objectMapper = objectMapper;
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        if (!properties.isEnabled() || "OPTIONS".equalsIgnoreCase(request.getMethod())) {
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

            if (requiresUserSession(request) && !context.isUser()) {
                writeError(response, HttpServletResponse.SC_UNAUTHORIZED, "unauthorized", "Login required");
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
        String sessionId = extractSessionId(request);
        if (sessionId != null) {
            java.util.Optional<AuthSessionService.SessionRecord> session = authSessionService.getSession(sessionId);
            if (session.isPresent()) {
                return new AuthContext(Long.toString(session.get().userId()), null);
            }
        }

        String adminId = request.getHeader(properties.getAdminHeader());
        String userId = null;
        if (!properties.isEnforceUserApi()) {
            userId = request.getHeader(properties.getUserHeader());
        }
        String authHeader = request.getHeader("Authorization");
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            String token = authHeader.substring("Bearer ".length()).trim();
            if (token.startsWith("admin:")) {
                adminId = token.substring("admin:".length());
            } else if (token.startsWith("user:") && !properties.isEnforceUserApi()) {
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

    private String extractSessionId(HttpServletRequest request) {
        String headerName = properties.getSessionHeader();
        if (headerName != null && !headerName.isBlank()) {
            String raw = request.getHeader(headerName);
            if (raw != null && !raw.isBlank()) {
                return raw.trim();
            }
        }
        String authHeader = request.getHeader("Authorization");
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            String token = authHeader.substring("Bearer ".length()).trim();
            if (token.startsWith("session:")) {
                String sessionId = token.substring("session:".length()).trim();
                if (!sessionId.isBlank()) {
                    return sessionId;
                }
            }
        }
        return null;
    }

    private boolean isAdminPath(HttpServletRequest request) {
        String path = request.getRequestURI();
        return path != null && path.startsWith("/admin");
    }

    private boolean requiresUserSession(HttpServletRequest request) {
        String path = request.getRequestURI();
        if (path == null || path.isBlank()) {
            return false;
        }
        if ("/auth/session".equals(path) || "/v1/auth/session".equals(path)) {
            return true;
        }
        if ("/auth/logout".equals(path) || "/v1/auth/logout".equals(path)) {
            return true;
        }
        if (!properties.isEnforceUserApi()) {
            return false;
        }
        String userApiPrefix = properties.getUserApiPrefix();
        if (userApiPrefix == null || userApiPrefix.isBlank()) {
            return false;
        }
        return path.startsWith(userApiPrefix);
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
