package com.bsl.bff.refund;

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

class RefundProxyControllerTest {
    private final RefundServiceClient refundServiceClient = mock(RefundServiceClient.class);
    private final RefundProxyController controller = new RefundProxyController(refundServiceClient);

    @AfterEach
    void tearDown() {
        RequestContextHolder.clear();
    }

    @Test
    void publicRefundCreateDelegatesToRefundService() {
        RequestContext context = new RequestContext("request-1", "trace-1", null, 1L);
        RequestContextHolder.set(context);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/v1/refunds");
        request.addHeader("Idempotency-Key", "refund:create:1");

        when(refundServiceClient.exchange(
            eq(HttpMethod.POST),
            eq("/api/v1/refunds"),
            eq("{}"),
            eq(context),
            eq("refund:create:1")
        )).thenReturn(ResponseEntity.ok("{\"status\":\"REQUESTED\"}"));

        ResponseEntity<String> response = controller.proxyUser(request, "{}");

        assertThat(response.getBody()).isEqualTo("{\"status\":\"REQUESTED\"}");
        verify(refundServiceClient).exchange(
            eq(HttpMethod.POST),
            eq("/api/v1/refunds"),
            eq("{}"),
            eq(context),
            eq("refund:create:1")
        );
    }

    @Test
    void adminRefundProcessPreservesQueryAndIdempotencyKey() {
        RequestContext context = new RequestContext("request-1", "trace-1", null, 1L);
        RequestContextHolder.set(context);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/admin/refunds/ref-1/process");
        request.setQueryString("dryRun=false");
        request.addHeader("Idempotency-Key", "refund:process:1");

        when(refundServiceClient.exchange(
            eq(HttpMethod.POST),
            eq("/admin/refunds/ref-1/process?dryRun=false"),
            eq("{}"),
            eq(context),
            eq("refund:process:1")
        )).thenReturn(ResponseEntity.ok("{\"status\":\"COMPLETED\"}"));

        ResponseEntity<String> response = controller.proxyAdmin(request, "{}");

        assertThat(response.getBody()).isEqualTo("{\"status\":\"COMPLETED\"}");
        verify(refundServiceClient).exchange(
            eq(HttpMethod.POST),
            eq("/admin/refunds/ref-1/process?dryRun=false"),
            eq("{}"),
            eq(context),
            eq("refund:process:1")
        );
    }
}
