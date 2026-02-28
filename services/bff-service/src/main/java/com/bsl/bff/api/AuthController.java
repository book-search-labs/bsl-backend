package com.bsl.bff.api;

import com.bsl.bff.api.dto.BffAuthLoginRequest;
import com.bsl.bff.common.BadRequestException;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.common.UnauthorizedException;
import com.bsl.bff.security.AuthProperties;
import com.bsl.bff.security.AuthSessionService;
import jakarta.servlet.http.HttpServletRequest;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthController {
    private final AuthSessionService authSessionService;
    private final AuthProperties authProperties;

    public AuthController(AuthSessionService authSessionService, AuthProperties authProperties) {
        this.authSessionService = authSessionService;
        this.authProperties = authProperties;
    }

    @PostMapping({"/auth/login", "/v1/auth/login"})
    public Map<String, Object> login(@RequestBody(required = false) BffAuthLoginRequest request) {
        if (request == null) {
            throw new BadRequestException("request body is required");
        }
        String email = request.getEmail() == null ? "" : request.getEmail().trim();
        String password = request.getPassword() == null ? "" : request.getPassword();
        if (email.isBlank() || password.isBlank()) {
            throw new BadRequestException("email and password are required");
        }
        AuthSessionService.SessionRecord session = authSessionService.login(email, password);
        return buildSessionResponse(session);
    }

    @GetMapping({"/auth/session", "/v1/auth/session"})
    public Map<String, Object> getSession(HttpServletRequest request) {
        String sessionId = resolveSessionIdHeader(request);
        AuthSessionService.SessionRecord session = authSessionService.getSession(sessionId)
            .orElseThrow(() -> new UnauthorizedException("로그인이 필요합니다."));
        return buildSessionResponse(session);
    }

    @PostMapping({"/auth/logout", "/v1/auth/logout"})
    public Map<String, Object> logout(HttpServletRequest request) {
        String sessionId = resolveSessionIdHeader(request);
        authSessionService.logout(sessionId);
        RequestContext context = RequestContextHolder.get();
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("version", "v1");
        response.put("trace_id", context == null ? null : context.getTraceId());
        response.put("request_id", context == null ? null : context.getRequestId());
        response.put("status", "ok");
        return response;
    }

    private String resolveSessionIdHeader(HttpServletRequest request) {
        String headerName = authProperties.getSessionHeader();
        String raw = headerName == null || headerName.isBlank() ? null : request.getHeader(headerName);
        if (raw == null || raw.isBlank()) {
            throw new UnauthorizedException("로그인이 필요합니다.");
        }
        return raw.trim();
    }

    private Map<String, Object> buildSessionResponse(AuthSessionService.SessionRecord session) {
        RequestContext context = RequestContextHolder.get();
        Map<String, Object> user = new LinkedHashMap<>();
        user.put("user_id", session.userId());
        user.put("email", session.email());
        user.put("name", session.name());
        user.put("membership_label", session.membershipLabel());
        user.put("phone", session.phone());

        Map<String, Object> sessionNode = new LinkedHashMap<>();
        sessionNode.put("session_id", session.sessionId());
        sessionNode.put("expires_at", Instant.ofEpochMilli(session.expiresAtMs()).toString());
        sessionNode.put("user", user);

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("version", "v1");
        response.put("trace_id", context == null ? null : context.getTraceId());
        response.put("request_id", context == null ? null : context.getRequestId());
        response.put("status", "ok");
        response.put("session", sessionNode);
        return response;
    }
}
