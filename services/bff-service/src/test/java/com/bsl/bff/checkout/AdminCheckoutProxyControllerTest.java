package com.bsl.bff.checkout;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockHttpServletRequest;

class AdminCheckoutProxyControllerTest {
    private final CheckoutOrchestratorClient orchestratorClient = mock(CheckoutOrchestratorClient.class);
    private final AdminCheckoutProxyController controller = new AdminCheckoutProxyController(orchestratorClient);

    @AfterEach
    void tearDown() {
        RequestContextHolder.clear();
    }

    @Test
    void listCheckoutsDelegatesToOrchestratorWithQuery() {
        RequestContext context = new RequestContext("request-1", "trace-1", null, 1L);
        RequestContextHolder.set(context);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/admin/checkouts");
        request.setQueryString("status=MANUAL_REVIEW_REQUIRED&limit=20");

        when(orchestratorClient.exchange(
            eq(HttpMethod.GET),
            eq("/internal/checkouts?status=MANUAL_REVIEW_REQUIRED&limit=20"),
            eq(null),
            eq(context),
            eq(null),
            eq(null)
        )).thenReturn(ResponseEntity.ok("{\"items\":[]}"));

        ResponseEntity<String> response = controller.listCheckouts(request);

        assertThat(response.getBody()).isEqualTo("{\"items\":[]}");
        verify(orchestratorClient).exchange(
            eq(HttpMethod.GET),
            eq("/internal/checkouts?status=MANUAL_REVIEW_REQUIRED&limit=20"),
            eq(null),
            eq(context),
            eq(null),
            eq(null)
        );
    }

    @Test
    void reconcileDelegatesToOrchestrator() {
        RequestContext context = new RequestContext("request-1", "trace-1", null, 1L);
        RequestContextHolder.set(context);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/admin/checkouts/1/steps/AUTHORIZE_PAYMENT/reconcile");

        when(orchestratorClient.exchange(
            eq(HttpMethod.POST),
            eq("/internal/checkouts/1/steps/AUTHORIZE_PAYMENT/reconcile"),
            eq("{}"),
            eq(context),
            eq(null),
            eq(null)
        )).thenReturn(ResponseEntity.ok("{\"action\":\"SCHEDULED_RECONCILIATION\"}"));

        ResponseEntity<String> response = controller.reconcileUnknownStep(request, "1", "AUTHORIZE_PAYMENT", "{}");

        assertThat(response.getBody()).isEqualTo("{\"action\":\"SCHEDULED_RECONCILIATION\"}");
        verify(orchestratorClient).exchange(
            eq(HttpMethod.POST),
            eq("/internal/checkouts/1/steps/AUTHORIZE_PAYMENT/reconcile"),
            eq("{}"),
            eq(context),
            eq(null),
            eq(null)
        );
    }
}
