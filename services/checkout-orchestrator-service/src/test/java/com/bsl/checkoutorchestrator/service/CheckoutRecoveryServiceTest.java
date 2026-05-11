package com.bsl.checkoutorchestrator.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.bsl.checkoutorchestrator.client.CheckoutDownstreamClient;
import com.bsl.checkoutorchestrator.domain.CheckoutSagaStatus;
import com.bsl.checkoutorchestrator.domain.CheckoutStepName;
import com.bsl.checkoutorchestrator.domain.CheckoutStepStatus;
import com.bsl.checkoutorchestrator.repository.InMemoryCheckoutSagaStore;
import com.bsl.checkoutorchestrator.repository.StepRecord;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.SimpleTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

class CheckoutRecoveryServiceTest {
    private final InMemoryCheckoutSagaStore store = new InMemoryCheckoutSagaStore();
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final FakeDownstreamClient downstreamClient = new FakeDownstreamClient();
    private final CheckoutSagaService sagaService = new CheckoutSagaService(store, objectMapper);
    private final CheckoutRecoveryService recoveryService = new CheckoutRecoveryService(
        store,
        downstreamClient,
        new TransactionTemplate(new NoOpTransactionManager()),
        objectMapper,
        Clock.fixed(Instant.parse("2026-05-08T00:00:00Z"), ZoneOffset.UTC)
    );

    @Test
    void manualRetryChangesOnlyFailedStepToReadyAndKeepsForwardIdempotencyKey() {
        sagaService.startCheckout(checkoutRequest("checkout:retry:1"), "trace-1", "request-1");
        StepRecord step = store.findStepBySagaIdAndName(1L, CheckoutStepName.AUTHORIZE_PAYMENT).orElseThrow();
        store.markStepFailedRetrying(step.id(), 1, Instant.parse("2026-05-08T00:00:01Z"), "downstream_http_500", "payment failed", Instant.now());

        Map<String, Object> response = recoveryService.retryStep(
            1L,
            "AUTHORIZE_PAYMENT",
            Map.of("reason", "retry payment", "operator_id", "ops-1"),
            "trace-2",
            "request-2"
        );

        StepRecord retried = store.findStepBySagaIdAndName(1L, CheckoutStepName.AUTHORIZE_PAYMENT).orElseThrow();
        assertThat(response)
            .containsEntry("before_status", "FAILED_RETRYING")
            .containsEntry("after_status", "READY")
            .containsEntry("idempotency_key", "checkout:1:AUTHORIZE_PAYMENT");
        assertThat(retried.status()).isEqualTo(CheckoutStepStatus.READY);
        assertThat(retried.idempotencyKey()).isEqualTo("checkout:1:AUTHORIZE_PAYMENT");
    }

    @Test
    void manualRetryRejectsSucceededStep() {
        sagaService.startCheckout(checkoutRequest("checkout:retry:2"), "trace-1", "request-1");
        StepRecord step = store.findStepBySagaIdAndName(1L, CheckoutStepName.CREATE_ORDER).orElseThrow();
        store.markStepSucceeded(step.id(), json(Map.of("order_id", "ord-1")), Instant.now());

        assertThatThrownBy(() -> recoveryService.retryStep(
            1L,
            "CREATE_ORDER",
            Map.of("reason", "bad retry", "operator_id", "ops-1"),
            "trace-2",
            "request-2"
        )).hasMessageContaining("manual retry");
    }

    @Test
    void unknownReconciliationKeepsUnknownStepAndClearsNextRetryAt() {
        sagaService.startCheckout(checkoutRequest("checkout:unknown:1"), "trace-1", "request-1");
        StepRecord step = store.findStepBySagaIdAndName(1L, CheckoutStepName.AUTHORIZE_PAYMENT).orElseThrow();
        store.markStepUnknown(step.id(), 1, Instant.parse("2026-05-08T01:00:00Z"), "payment_timeout", "timeout", Instant.now());

        Map<String, Object> response = recoveryService.reconcileUnknownStep(
            1L,
            "AUTHORIZE_PAYMENT",
            Map.of("reason", "check payment idempotency result", "operator_id", "ops-1"),
            "trace-2",
            "request-2"
        );

        StepRecord scheduled = store.findStepBySagaIdAndName(1L, CheckoutStepName.AUTHORIZE_PAYMENT).orElseThrow();
        assertThat(response)
            .containsEntry("action", "SCHEDULED_RECONCILIATION")
            .containsEntry("before_status", "UNKNOWN")
            .containsEntry("after_status", "UNKNOWN");
        assertThat(scheduled.status()).isEqualTo(CheckoutStepStatus.UNKNOWN);
        assertThat(scheduled.nextRetryAt()).isNull();
    }

    @Test
    void unknownReconciliationRejectsNonUnknownStep() {
        sagaService.startCheckout(checkoutRequest("checkout:unknown:2"), "trace-1", "request-1");

        assertThatThrownBy(() -> recoveryService.reconcileUnknownStep(
            1L,
            "AUTHORIZE_PAYMENT",
            Map.of("reason", "bad reconcile", "operator_id", "ops-1"),
            "trace-2",
            "request-2"
        )).hasMessageContaining("UNKNOWN");
    }

    @Test
    void cancelCompensatesSucceededStepsInReverseOrderWithCompensateKeys() {
        sagaService.startCheckout(checkoutRequest("checkout:cancel:1"), "trace-1", "request-1");
        markSucceeded(CheckoutStepName.CREATE_ORDER, Map.of("order_id", "ord-1"));
        markSucceeded(CheckoutStepName.RESERVE_STOCK, Map.of("reservation_id", "inv-res-1"));
        markSucceeded(CheckoutStepName.AUTHORIZE_PAYMENT, Map.of("payment_id", "pay-1"));
        markSucceeded(CheckoutStepName.REQUEST_SHIPMENT, Map.of("shipment_id", "ship-1"));
        store.updateSagaContext(1L, json(Map.of(
            "order_id", "ord-1",
            "inventory_reservation_id", "inv-res-1",
            "payment_id", "pay-1",
            "shipment_request_id", "ship-1"
        )), Instant.now());
        store.updateSagaStatus(1L, CheckoutSagaStatus.SUCCEEDED, null, null, null, Instant.now());

        Map<String, Object> response = recoveryService.cancelCheckout(
            1L,
            Map.of("reason", "user cancel", "operator_id", "ops-1"),
            "trace-2",
            "request-2"
        );

        assertThat(response).containsEntry("status", "CANCELLED");
        assertThat(downstreamClient.compensationCalls)
            .extracting(CompensationCall::stepName)
            .containsExactly(
                CheckoutStepName.REQUEST_SHIPMENT,
                CheckoutStepName.AUTHORIZE_PAYMENT,
                CheckoutStepName.RESERVE_STOCK
            );
        assertThat(downstreamClient.compensationCalls)
            .extracting(CompensationCall::idempotencyKey)
            .containsExactly(
                "checkout:1:REQUEST_SHIPMENT:compensate",
                "checkout:1:AUTHORIZE_PAYMENT:compensate",
                "checkout:1:RESERVE_STOCK:compensate"
            );
        assertThat(store.findStepBySagaIdAndName(1L, CheckoutStepName.REQUEST_SHIPMENT).orElseThrow().status())
            .isEqualTo(CheckoutStepStatus.COMPENSATED);
    }

    @Test
    void repeatedCancelDoesNotRunCompensationAgainAfterCancelled() {
        sagaService.startCheckout(checkoutRequest("checkout:cancel:2"), "trace-1", "request-1");
        markSucceeded(CheckoutStepName.AUTHORIZE_PAYMENT, Map.of("payment_id", "pay-1"));
        store.updateSagaContext(1L, json(Map.of("payment_id", "pay-1")), Instant.now());
        store.updateSagaStatus(1L, CheckoutSagaStatus.SUCCEEDED, null, null, null, Instant.now());

        recoveryService.cancelCheckout(1L, Map.of("reason", "first", "operator_id", "ops-1"), "trace-2", "request-2");
        recoveryService.cancelCheckout(1L, Map.of("reason", "second", "operator_id", "ops-1"), "trace-3", "request-3");

        assertThat(downstreamClient.compensationCalls).hasSize(1);
    }

    private void markSucceeded(CheckoutStepName stepName, Map<String, Object> response) {
        StepRecord step = store.findStepBySagaIdAndName(1L, stepName).orElseThrow();
        store.markStepSucceeded(step.id(), json(response), Instant.now());
    }

    private Map<String, Object> checkoutRequest(String checkoutKey) {
        return Map.of(
            "checkout_key", checkoutKey,
            "user_id", "101",
            "items", List.of(Map.of("book_id", "book-1", "title", "Book", "quantity", 1, "unit_price", 12000)),
            "payment", Map.of("amount", 12000, "currency", "KRW", "method", "MOCK"),
            "shipping_address", Map.of("recipient", "tester", "line1", "Seoul")
        );
    }

    private String json(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static class FakeDownstreamClient implements CheckoutDownstreamClient {
        private final List<CompensationCall> compensationCalls = new ArrayList<>();

        @Override
        public Map<String, Object> execute(
            CheckoutStepName stepName,
            Map<String, Object> request,
            String idempotencyKey,
            String traceId,
            String requestId
        ) {
            return Map.of();
        }

        @Override
        public Optional<Map<String, Object>> reconcile(
            CheckoutStepName stepName,
            String idempotencyKey,
            String traceId,
            String requestId
        ) {
            return Optional.empty();
        }

        @Override
        public Map<String, Object> compensate(
            CheckoutStepName stepName,
            Map<String, Object> request,
            String idempotencyKey,
            String traceId,
            String requestId
        ) {
            compensationCalls.add(new CompensationCall(stepName, idempotencyKey, request));
            return Map.of("status", "COMPENSATED", "step_name", stepName.name());
        }
    }

    private record CompensationCall(
        CheckoutStepName stepName,
        String idempotencyKey,
        Map<String, Object> request
    ) {
    }

    private static class NoOpTransactionManager implements PlatformTransactionManager {
        @Override
        public TransactionStatus getTransaction(TransactionDefinition definition) {
            return new SimpleTransactionStatus();
        }

        @Override
        public void commit(TransactionStatus status) {
        }

        @Override
        public void rollback(TransactionStatus status) {
        }
    }
}
