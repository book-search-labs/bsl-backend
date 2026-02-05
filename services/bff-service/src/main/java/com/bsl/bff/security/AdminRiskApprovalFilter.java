package com.bsl.bff.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 35)
public class AdminRiskApprovalFilter extends OncePerRequestFilter {
    private final AdminApprovalRepository repository;

    @Value("${security.admin-approval.enabled:false}")
    private boolean enabled;

    @Value("${security.admin-approval.risky-paths:}")
    private String riskyPaths;

    public AdminRiskApprovalFilter(AdminApprovalRepository repository) {
        this.repository = repository;
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        if (!enabled || !isAdminPath(request) || isSafeMethod(request.getMethod()) || !isRisky(request.getRequestURI())) {
            filterChain.doFilter(request, response);
            return;
        }

        String approvalHeader = request.getHeader("x-approval-id");
        if (approvalHeader == null || approvalHeader.isBlank()) {
            respond(response, HttpStatus.PRECONDITION_REQUIRED, "approval_required", "admin approval required");
            return;
        }

        long approvalId;
        try {
            approvalId = Long.parseLong(approvalHeader.trim());
        } catch (NumberFormatException ex) {
            respond(response, HttpStatus.BAD_REQUEST, "invalid_approval_id", "x-approval-id must be numeric");
            return;
        }

        Map<String, Object> approval = repository.findApproval(approvalId);
        if (approval == null) {
            respond(response, HttpStatus.FORBIDDEN, "approval_not_found", "approval not found");
            return;
        }

        if (!isApproved(approval)) {
            respond(response, HttpStatus.FORBIDDEN, "approval_not_approved", "approval not approved");
            return;
        }

        if (isExpired(approval)) {
            respond(response, HttpStatus.FORBIDDEN, "approval_expired", "approval expired");
            return;
        }

        String expectedAction = request.getMethod() + " " + request.getRequestURI();
        String action = approval.get("action") == null ? null : String.valueOf(approval.get("action"));
        if (action != null && !action.isBlank() && !action.equals(expectedAction)) {
            respond(response, HttpStatus.FORBIDDEN, "approval_mismatch", "approval action mismatch");
            return;
        }

        AuthContext auth = AuthContextHolder.get();
        if (auth != null && auth.isAdmin()) {
            try {
                long requestedAdmin = Long.parseLong(String.valueOf(approval.get("requested_by_admin_id")));
                if (requestedAdmin != Long.parseLong(auth.getAdminId())) {
                    respond(response, HttpStatus.FORBIDDEN, "approval_actor_mismatch", "approval actor mismatch");
                    return;
                }
            } catch (NumberFormatException ex) {
                // ignore mismatch if admin ids are not numeric
            }
        }

        repository.markUsed(approvalId);
        filterChain.doFilter(request, response);
    }

    private void respond(HttpServletResponse response, HttpStatus status, String code, String message) throws IOException {
        response.setStatus(status.value());
        response.setContentType("application/json");
        response.getWriter().write(String.format("{\"error\":{\"code\":\"%s\",\"message\":\"%s\"}}", code, message));
    }

    private boolean isRisky(String path) {
        if (path == null) {
            return false;
        }
        List<Pattern> patterns = Arrays.stream(riskyPaths.split(","))
            .map(String::trim)
            .filter(value -> !value.isEmpty())
            .map(Pattern::compile)
            .collect(Collectors.toList());
        if (patterns.isEmpty()) {
            return false;
        }
        return patterns.stream().anyMatch(pattern -> pattern.matcher(path).matches());
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

    private boolean isApproved(Map<String, Object> approval) {
        Object status = approval.get("status");
        return status != null && "APPROVED".equalsIgnoreCase(String.valueOf(status));
    }

    private boolean isExpired(Map<String, Object> approval) {
        Instant expiresAt = toInstant(approval.get("expires_at"));
        return expiresAt != null && expiresAt.isBefore(Instant.now());
    }

    private Instant toInstant(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Timestamp ts) {
            return ts.toInstant();
        }
        if (value instanceof LocalDateTime ldt) {
            return ldt.toInstant(ZoneOffset.UTC);
        }
        return null;
    }
}
