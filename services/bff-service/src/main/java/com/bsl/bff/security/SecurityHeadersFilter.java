package com.bsl.bff.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 5)
public class SecurityHeadersFilter extends OncePerRequestFilter {

    @Value("${security.headers.enabled:true}")
    private boolean enabled;

    @Value("${security.headers.frame-options:DENY}")
    private String frameOptions;

    @Value("${security.headers.referrer-policy:no-referrer}")
    private String referrerPolicy;

    @Value("${security.headers.permissions-policy:geolocation=(), microphone=(), camera=()}")
    private String permissionsPolicy;

    @Value("${security.headers.cross-origin-opener-policy:same-origin}")
    private String crossOriginOpenerPolicy;

    @Value("${security.headers.cross-origin-resource-policy:same-site}")
    private String crossOriginResourcePolicy;

    @Value("${security.headers.hsts-enabled:false}")
    private boolean hstsEnabled;

    @Value("${security.headers.hsts-max-age:31536000}")
    private long hstsMaxAge;

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        if (enabled) {
            response.setHeader("X-Content-Type-Options", "nosniff");
            response.setHeader("X-Frame-Options", frameOptions);
            response.setHeader("Referrer-Policy", referrerPolicy);
            response.setHeader("Permissions-Policy", permissionsPolicy);
            response.setHeader("Cross-Origin-Opener-Policy", crossOriginOpenerPolicy);
            response.setHeader("Cross-Origin-Resource-Policy", crossOriginResourcePolicy);
            if (hstsEnabled && request.isSecure()) {
                response.setHeader("Strict-Transport-Security", "max-age=" + hstsMaxAge + "; includeSubDomains");
            }
        }
        filterChain.doFilter(request, response);
    }
}
