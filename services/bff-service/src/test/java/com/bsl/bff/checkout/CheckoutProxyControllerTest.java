package com.bsl.bff.checkout;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.bff.client.CommerceServiceClient;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockHttpServletRequest;

class CheckoutProxyControllerTest {
    private final CheckoutOrchestratorClient orchestratorClient = mock(CheckoutOrchestratorClient.class);
    private final CommerceServiceClient commerceServiceClient = mock(CommerceServiceClient.class);
    private final CheckoutProperties properties = new CheckoutProperties();
    private final CheckoutProxyController controller = new CheckoutProxyController(
        orchestratorClient,
        commerceServiceClient,
        properties
    );

    @AfterEach
    void tearDown() {
        RequestContextHolder.clear();
    }

    @Test
    void startCheckoutDelegatesToOrchestratorByDefault() {
        RequestContext context = new RequestContext("request-1", "trace-1", null, 1L);
        RequestContextHolder.set(context);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/v1/checkout");
        request.addHeader("Idempotency-Key", "checkout-key-1");
        request.addHeader("x-session-id", "session-1");

        when(orchestratorClient.exchange(
            eq(HttpMethod.POST),
            eq("/internal/checkouts"),
            eq("{}"),
            eq(context),
            eq("checkout-key-1"),
            eq("session-1")
        )).thenReturn(ResponseEntity.ok("{\"status\":\"PENDING\"}"));

        ResponseEntity<String> response = controller.startCheckout(request, "{}");

        assertThat(response.getBody()).isEqualTo("{\"status\":\"PENDING\"}");
        verify(orchestratorClient).exchange(
            eq(HttpMethod.POST),
            eq("/internal/checkouts"),
            eq("{}"),
            eq(context),
            eq("checkout-key-1"),
            eq("session-1")
        );
    }

    @Test
    void legacyBackendDelegatesToCommerceService() {
        properties.setBackend("legacy");
        RequestContext context = new RequestContext("request-1", "trace-1", null, 1L);
        RequestContextHolder.set(context);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/v1/checkout");
        request.setQueryString("debug=true");

        when(commerceServiceClient.exchange(eq(HttpMethod.POST), eq("/api/v1/checkout?debug=true"), eq("{}"), eq(context)))
            .thenReturn(ResponseEntity.ok("{\"legacy\":true}"));

        ResponseEntity<String> response = controller.startCheckout(request, "{}");

        assertThat(response.getBody()).isEqualTo("{\"legacy\":true}");
        verify(commerceServiceClient).exchange(eq(HttpMethod.POST), eq("/api/v1/checkout?debug=true"), eq("{}"), eq(context));
    }
}
