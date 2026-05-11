package com.bsl.checkoutorchestrator.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.bsl.checkoutorchestrator.repository.InMemoryCheckoutSagaStore;
import com.bsl.checkoutorchestrator.service.CheckoutSagaService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class CheckoutControllerTest {
    private final CheckoutController controller = new CheckoutController(
        new CheckoutSagaService(new InMemoryCheckoutSagaStore(), new ObjectMapper()),
        null
    );

    @Test
    void startCheckoutReturnsSagaShape() {
        Map<String, Object> response = controller.startCheckout(
            checkoutRequest("checkout:test:1"),
            "trace-1",
            "request-1"
        );

        assertThat(response)
            .containsEntry("checkout_key", "checkout:test:1")
            .containsEntry("user_id", "101")
            .containsEntry("status", "PENDING")
            .containsEntry("current_step", null)
            .containsEntry("mode", "db");
        assertThat(response.get("checkout_id")).isNotNull();
        assertThat(response.get("trace_id")).isEqualTo("trace-1");
        assertThat(response.get("request_id")).isEqualTo("request-1");

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> steps = (List<Map<String, Object>>) response.get("steps");
        assertThat(steps)
            .extracting(step -> step.get("step_name"))
            .containsExactly("CREATE_ORDER", "RESERVE_STOCK", "AUTHORIZE_PAYMENT", "REQUEST_SHIPMENT");
        assertThat(steps).allSatisfy(step -> assertThat(step).containsEntry("status", "READY"));
        assertThat(steps).allSatisfy(step -> assertThat(step.get("idempotency_key").toString())
            .startsWith("checkout:" + response.get("checkout_id") + ":"));
    }

    private Map<String, Object> checkoutRequest(String checkoutKey) {
        return Map.of(
            "checkout_key", checkoutKey,
            "user_id", "101",
            "items", List.of(Map.of("book_id", "book-1", "quantity", 1)),
            "payment", Map.of("amount", 12000, "currency", "KRW", "method", "MOCK"),
            "shipping_address", Map.of("recipient", "tester", "line1", "Seoul")
        );
    }
}
