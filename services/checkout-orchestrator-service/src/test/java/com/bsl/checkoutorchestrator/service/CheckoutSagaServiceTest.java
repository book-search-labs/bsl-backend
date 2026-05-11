package com.bsl.checkoutorchestrator.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.bsl.checkoutorchestrator.common.ApiException;
import com.bsl.checkoutorchestrator.repository.InMemoryCheckoutSagaStore;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class CheckoutSagaServiceTest {
    private final InMemoryCheckoutSagaStore store = new InMemoryCheckoutSagaStore();
    private final CheckoutSagaService service = new CheckoutSagaService(
        store,
        new ObjectMapper(),
        Clock.fixed(Instant.parse("2026-05-08T00:00:00Z"), ZoneOffset.UTC)
    );

    @Test
    void startCheckoutCreatesSagaStepsAndStartedOutboxEvent() {
        Map<String, Object> response = service.startCheckout(checkoutRequest("checkout:key:1"), "trace-1", "request-1");

        assertThat(response)
            .containsEntry("checkout_key", "checkout:key:1")
            .containsEntry("status", "PENDING")
            .containsEntry("mode", "db");
        assertThat(response.get("checkout_id")).isEqualTo(1L);

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> steps = (List<Map<String, Object>>) response.get("steps");
        assertThat(steps).hasSize(4);
        assertThat(steps)
            .extracting(step -> step.get("step_name"))
            .containsExactly("CREATE_ORDER", "RESERVE_STOCK", "AUTHORIZE_PAYMENT", "REQUEST_SHIPMENT");
        assertThat(steps)
            .extracting(step -> step.get("step_category"))
            .containsExactly("COMPENSATABLE", "COMPENSATABLE", "COMPENSATABLE", "RETRIABLE");
        assertThat(steps)
            .extracting(step -> step.get("recovery_policy"))
            .containsExactly("BACKWARD", "BACKWARD", "BACKWARD", "FORWARD");
        assertThat(steps)
            .extracting(step -> step.get("idempotency_key"))
            .containsExactly(
                "checkout:1:CREATE_ORDER",
                "checkout:1:RESERVE_STOCK",
                "checkout:1:AUTHORIZE_PAYMENT",
                "checkout:1:REQUEST_SHIPMENT"
            );

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> outboxEvents = (List<Map<String, Object>>) response.get("outbox_events");
        assertThat(outboxEvents).hasSize(1);
        assertThat(outboxEvents.get(0))
            .containsEntry("event_type", "CHECKOUT_STARTED")
            .containsEntry("event_key", "checkout:1:CHECKOUT_STARTED:v1")
            .containsEntry("status", "READY");

        @SuppressWarnings("unchecked")
        Map<String, Object> payload = (Map<String, Object>) outboxEvents.get(0).get("payload");
        assertThat(payload)
            .containsEntry("event_version", "v1")
            .containsEntry("checkout_id", 1)
            .containsEntry("checkout_key", "checkout:key:1")
            .containsEntry("trace_id", "trace-1")
            .containsEntry("request_id", "request-1")
            .containsEntry("occurred_at", "2026-05-08T00:00:00Z");
    }

    @Test
    void duplicateCheckoutKeyReturnsExistingSaga() {
        Map<String, Object> first = service.startCheckout(checkoutRequest("checkout:key:2"), "trace-1", "request-1");
        Map<String, Object> second = service.startCheckout(checkoutRequest("checkout:key:2"), "trace-2", "request-2");

        assertThat(second.get("checkout_id")).isEqualTo(first.get("checkout_id"));
        assertThat(second.get("trace_id")).isEqualTo("trace-2");
        assertThat(store.findStepsBySagaId(1L)).hasSize(4);
        assertThat(store.findOutboxEventsByAggregate("CHECKOUT_SAGA", 1L)).hasSize(1);
    }

    @Test
    void listCheckoutsFiltersByStatusAndIncludesFailedStepSummary() {
        service.startCheckout(checkoutRequest("checkout:list:1"), "trace-1", "request-1");
        service.startCheckout(checkoutRequest("checkout:list:2"), "trace-1", "request-1");
        store.updateSagaStatus(2L, com.bsl.checkoutorchestrator.domain.CheckoutSagaStatus.MANUAL_REVIEW_REQUIRED,
            com.bsl.checkoutorchestrator.domain.CheckoutStepName.AUTHORIZE_PAYMENT, "payment_failed", "payment failed", Instant.now());
        com.bsl.checkoutorchestrator.repository.StepRecord step =
            store.findStepBySagaIdAndName(2L, com.bsl.checkoutorchestrator.domain.CheckoutStepName.AUTHORIZE_PAYMENT).orElseThrow();
        store.markStepManualReview(step.id(), "payment_failed", "payment failed", Instant.now());

        Map<String, Object> response = service.listCheckouts("MANUAL_REVIEW_REQUIRED", 10, "trace-2", "request-2");

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> items = (List<Map<String, Object>>) response.get("items");
        assertThat(items).hasSize(1);
        assertThat(items.get(0))
            .containsEntry("checkout_id", 2L)
            .containsEntry("status", "MANUAL_REVIEW_REQUIRED");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> failedSteps = (List<Map<String, Object>>) items.get(0).get("failed_steps");
        assertThat(failedSteps).hasSize(1);
        assertThat(failedSteps.get(0)).containsEntry("step_name", "AUTHORIZE_PAYMENT");
    }

    @Test
    void startCheckoutRejectsInvalidPayload() {
        assertThatThrownBy(() -> service.startCheckout(Map.of("checkout_key", "checkout:key:3"), "trace-1", "request-1"))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("user_id");
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
