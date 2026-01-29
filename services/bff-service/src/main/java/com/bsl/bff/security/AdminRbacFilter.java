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
@Order(Ordered.HIGHEST_PRECEDENCE + 30)
public class AdminRbacFilter extends OncePerRequestFilter {
    private final RbacProperties properties;
    private final AdminPermissionService permissionService;
    private final PermissionResolver resolver;
    private final ObjectMapper objectMapper;

    public AdminRbacFilter(
        RbacProperties properties,
        AdminPermissionService permissionService,
        PermissionResolver resolver,
        ObjectMapper objectMapper
    ) {
        this.properties = properties;
        this.permissionService = permissionService;
        this.resolver = resolver;
        this.objectMapper = objectMapper;
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        if (!properties.isEnabled() || !isAdminPath(request)) {
            filterChain.doFilter(request, response);
            return;
        }

        String permission = resolver.resolve(request.getRequestURI());
        if (permission == null) {
            filterChain.doFilter(request, response);
            return;
        }

        AuthContext authContext = AuthContextHolder.get();
        if (authContext == null || !authContext.isAdmin()) {
            writeError(response, HttpServletResponse.SC_UNAUTHORIZED, "unauthorized", "Admin auth required");
            return;
        }

        if (!permissionService.hasPermission(authContext.getAdminId(), permission)) {
            writeError(response, HttpServletResponse.SC_FORBIDDEN, "forbidden", "Permission denied");
            return;
        }

        filterChain.doFilter(request, response);
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
