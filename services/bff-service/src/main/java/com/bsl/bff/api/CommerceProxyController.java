package com.bsl.bff.api;

import com.bsl.bff.client.CommerceServiceClient;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CommerceProxyController {
    private final CommerceServiceClient commerceServiceClient;

    public CommerceProxyController(CommerceServiceClient commerceServiceClient) {
        this.commerceServiceClient = commerceServiceClient;
    }

    @RequestMapping(value = "/api/v1/**", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> proxyUser(HttpServletRequest request, @RequestBody(required = false) String body) {
        return forward(request, body);
    }

    @RequestMapping(
        value = {
            "/admin/sellers/**",
            "/admin/skus/**",
            "/admin/offers/**",
            "/admin/inventory/**",
            "/admin/payments/**",
            "/admin/refunds/**",
            "/admin/settlements/**",
            "/admin/shipments/**",
            "/admin/support/**"
        },
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<String> proxyAdmin(HttpServletRequest request, @RequestBody(required = false) String body) {
        return forward(request, body);
    }

    private ResponseEntity<String> forward(HttpServletRequest request, String body) {
        RequestContext context = RequestContextHolder.get();
        String path = request.getRequestURI();
        String query = request.getQueryString();
        if (query != null && !query.isBlank()) {
            path = path + "?" + query;
        }
        HttpMethod method = resolveMethod(request.getMethod());
        ResponseEntity<String> downstream = commerceServiceClient.exchange(method, path, body, context);
        return ResponseEntity.status(downstream.getStatusCode())
            .contentType(MediaType.APPLICATION_JSON)
            .body(downstream.getBody());
    }

    private HttpMethod resolveMethod(String method) {
        try {
            return HttpMethod.valueOf(method);
        } catch (IllegalArgumentException ex) {
            return HttpMethod.GET;
        }
    }
}
