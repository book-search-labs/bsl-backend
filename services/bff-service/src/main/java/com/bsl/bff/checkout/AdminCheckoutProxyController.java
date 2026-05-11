package com.bsl.bff.checkout;

import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AdminCheckoutProxyController {
    private final CheckoutOrchestratorClient checkoutOrchestratorClient;

    public AdminCheckoutProxyController(CheckoutOrchestratorClient checkoutOrchestratorClient) {
        this.checkoutOrchestratorClient = checkoutOrchestratorClient;
    }

    @GetMapping(value = "/admin/checkouts", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> listCheckouts(HttpServletRequest request) {
        return forward(request, HttpMethod.GET, "/internal/checkouts", null);
    }

    @GetMapping(value = "/admin/checkouts/{checkoutId}", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> getCheckout(HttpServletRequest request, @PathVariable String checkoutId) {
        return forward(request, HttpMethod.GET, "/internal/checkouts/" + checkoutId, null);
    }

    @PostMapping(value = "/admin/checkouts/{checkoutId}/steps/{stepName}/retry", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> retryStep(
        HttpServletRequest request,
        @PathVariable String checkoutId,
        @PathVariable String stepName,
        @RequestBody(required = false) String body
    ) {
        return forward(request, HttpMethod.POST, "/internal/checkouts/" + checkoutId + "/steps/" + stepName + "/retry", body);
    }

    @PostMapping(value = "/admin/checkouts/{checkoutId}/steps/{stepName}/reconcile", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> reconcileUnknownStep(
        HttpServletRequest request,
        @PathVariable String checkoutId,
        @PathVariable String stepName,
        @RequestBody(required = false) String body
    ) {
        return forward(request, HttpMethod.POST, "/internal/checkouts/" + checkoutId + "/steps/" + stepName + "/reconcile", body);
    }

    @PostMapping(value = "/admin/checkouts/{checkoutId}/cancel", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> cancelCheckout(
        HttpServletRequest request,
        @PathVariable String checkoutId,
        @RequestBody(required = false) String body
    ) {
        return forward(request, HttpMethod.POST, "/internal/checkouts/" + checkoutId + "/cancel", body);
    }

    private ResponseEntity<String> forward(HttpServletRequest request, HttpMethod method, String orchestratorPath, String body) {
        RequestContext context = RequestContextHolder.get();
        ResponseEntity<String> downstream = checkoutOrchestratorClient.exchange(
            method,
            appendQuery(request, orchestratorPath),
            body,
            context,
            request.getHeader("Idempotency-Key"),
            request.getHeader("x-session-id")
        );
        return ResponseEntity.status(downstream.getStatusCode())
            .contentType(MediaType.APPLICATION_JSON)
            .body(downstream.getBody());
    }

    private String appendQuery(HttpServletRequest request, String path) {
        String query = request.getQueryString();
        if (query == null || query.isBlank()) {
            return path;
        }
        return path + "?" + query;
    }
}
