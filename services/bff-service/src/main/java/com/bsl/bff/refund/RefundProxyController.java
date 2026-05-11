package com.bsl.bff.refund;

import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RefundProxyController {
    private final RefundServiceClient refundServiceClient;

    public RefundProxyController(RefundServiceClient refundServiceClient) {
        this.refundServiceClient = refundServiceClient;
    }

    @RequestMapping(value = {"/api/v1/refunds", "/api/v1/refunds/**"}, produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> proxyUser(HttpServletRequest request, @RequestBody(required = false) String body) {
        return forward(request, body);
    }

    @RequestMapping(value = {"/admin/refunds", "/admin/refunds/**"}, produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> proxyAdmin(HttpServletRequest request, @RequestBody(required = false) String body) {
        return forward(request, body);
    }

    private ResponseEntity<String> forward(HttpServletRequest request, String body) {
        RequestContext context = RequestContextHolder.get();
        ResponseEntity<String> downstream = refundServiceClient.exchange(
            resolveMethod(request.getMethod()),
            appendQuery(request),
            body,
            context,
            request.getHeader("Idempotency-Key")
        );
        return ResponseEntity.status(downstream.getStatusCode())
            .contentType(MediaType.APPLICATION_JSON)
            .body(downstream.getBody());
    }

    private String appendQuery(HttpServletRequest request) {
        String path = request.getRequestURI();
        String query = request.getQueryString();
        if (query == null || query.isBlank()) {
            return path;
        }
        return path + "?" + query;
    }

    private HttpMethod resolveMethod(String method) {
        try {
            return HttpMethod.valueOf(method);
        } catch (IllegalArgumentException ex) {
            return HttpMethod.GET;
        }
    }
}
