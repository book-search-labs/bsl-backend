package com.bsl.bff.audit;

import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.security.AuthContext;
import com.bsl.bff.security.AuthContextHolder;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingRequestWrapper;
import org.springframework.web.util.ContentCachingResponseWrapper;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 40)
public class AdminAuditFilter extends OncePerRequestFilter {
    private static final int MAX_BODY_BYTES = 10_000;
    private final AuditLogRepository repository;

    public AdminAuditFilter(AuditLogRepository repository) {
        this.repository = repository;
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        if (!isAdminPath(request) || isSafeMethod(request.getMethod())) {
            filterChain.doFilter(request, response);
            return;
        }

        ContentCachingRequestWrapper wrappedRequest = new ContentCachingRequestWrapper(request);
        ContentCachingResponseWrapper wrappedResponse = new ContentCachingResponseWrapper(response);
        try {
            filterChain.doFilter(wrappedRequest, wrappedResponse);
        } finally {
            recordAudit(wrappedRequest);
            wrappedResponse.copyBodyToResponse();
        }
    }

    private void recordAudit(ContentCachingRequestWrapper request) {
        AuthContext authContext = AuthContextHolder.get();
        if (authContext == null || !authContext.isAdmin()) {
            return;
        }
        long adminId;
        try {
            adminId = Long.parseLong(authContext.getAdminId());
        } catch (NumberFormatException ex) {
            return;
        }
        RequestContext context = RequestContextHolder.get();
        String body = readBody(request);
        repository.insert(
            adminId,
            request.getMethod() + " " + request.getRequestURI(),
            "admin_api",
            request.getRequestURI(),
            null,
            body,
            context == null ? null : context.getRequestId(),
            context == null ? null : context.getTraceId(),
            request.getRemoteAddr(),
            request.getHeader("User-Agent")
        );
    }

    private String readBody(ContentCachingRequestWrapper request) {
        byte[] buf = request.getContentAsByteArray();
        if (buf.length == 0) {
            return null;
        }
        int len = Math.min(buf.length, MAX_BODY_BYTES);
        return new String(buf, 0, len, StandardCharsets.UTF_8);
    }

    private boolean isAdminPath(HttpServletRequest request) {
        String path = request.getRequestURI();
        return path != null && path.startsWith("/admin");
    }

    private boolean isSafeMethod(String method) {
        return "GET".equalsIgnoreCase(method)
            || "HEAD".equalsIgnoreCase(method)
            || "OPTIONS".equalsIgnoreCase(method);
    }
}
