package com.bsl.bff.checkout;

import com.bsl.bff.client.CommerceServiceClient;
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
public class CheckoutProxyController {
    private final CheckoutOrchestratorClient checkoutOrchestratorClient;
    private final CommerceServiceClient commerceServiceClient;
    private final CheckoutProperties checkoutProperties;

    public CheckoutProxyController(
        CheckoutOrchestratorClient checkoutOrchestratorClient,
        CommerceServiceClient commerceServiceClient,
        CheckoutProperties checkoutProperties
    ) {
        this.checkoutOrchestratorClient = checkoutOrchestratorClient;
        this.commerceServiceClient = commerceServiceClient;
        this.checkoutProperties = checkoutProperties;
    }

    @PostMapping(value = "/v1/checkout", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> startCheckout(HttpServletRequest request, @RequestBody(required = false) String body) {
        return forward(request, HttpMethod.POST, "/internal/checkouts", "/api/v1/checkout", body);
    }

    @GetMapping(value = "/v1/checkout/{checkoutId}", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> getCheckout(HttpServletRequest request, @PathVariable String checkoutId) {
        return forward(request, HttpMethod.GET, "/internal/checkouts/" + checkoutId, "/api/v1/checkout/" + checkoutId, null);
    }

    @PostMapping(value = "/v1/checkout/{checkoutId}/steps/{stepName}/retry", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> retryStep(
        HttpServletRequest request,
        @PathVariable String checkoutId,
        @PathVariable String stepName,
        @RequestBody(required = false) String body
    ) {
        return forward(
            request,
            HttpMethod.POST,
            "/internal/checkouts/" + checkoutId + "/steps/" + stepName + "/retry",
            "/api/v1/checkout/" + checkoutId + "/steps/" + stepName + "/retry",
            body
        );
    }

    @PostMapping(value = "/v1/checkout/{checkoutId}/steps/{stepName}/reconcile", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> reconcileUnknownStep(
        HttpServletRequest request,
        @PathVariable String checkoutId,
        @PathVariable String stepName,
        @RequestBody(required = false) String body
    ) {
        return forward(
            request,
            HttpMethod.POST,
            "/internal/checkouts/" + checkoutId + "/steps/" + stepName + "/reconcile",
            "/api/v1/checkout/" + checkoutId + "/steps/" + stepName + "/reconcile",
            body
        );
    }

    @PostMapping(value = "/v1/checkout/{checkoutId}/cancel", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> cancelCheckout(
        HttpServletRequest request,
        @PathVariable String checkoutId,
        @RequestBody(required = false) String body
    ) {
        return forward(
            request,
            HttpMethod.POST,
            "/internal/checkouts/" + checkoutId + "/cancel",
            "/api/v1/checkout/" + checkoutId + "/cancel",
            body
        );
    }

    private ResponseEntity<String> forward(
        HttpServletRequest request,
        HttpMethod method,
        String orchestratorPath,
        String legacyPath,
        String body
    ) {
        RequestContext context = RequestContextHolder.get();
        ResponseEntity<String> downstream;
        if (checkoutProperties.useLegacy()) {
            downstream = commerceServiceClient.exchange(method, appendQuery(request, legacyPath), body, context);
        } else {
            downstream = checkoutOrchestratorClient.exchange(
                method,
                appendQuery(request, orchestratorPath),
                body,
                context,
                request.getHeader("Idempotency-Key"),
                request.getHeader("x-session-id")
            );
        }
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
