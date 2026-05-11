package com.bsl.checkoutorchestrator.worker;

import static org.assertj.core.api.Assertions.assertThat;

import com.bsl.checkoutorchestrator.client.CheckoutDownstreamClient;
import com.bsl.checkoutorchestrator.client.DownstreamCallException;
import com.bsl.checkoutorchestrator.config.CheckoutOrchestratorProperties;
import com.bsl.checkoutorchestrator.domain.CheckoutStepName;
import com.bsl.checkoutorchestrator.domain.CheckoutStepStatus;
import com.bsl.checkoutorchestrator.repository.InMemoryCheckoutSagaStore;
import com.bsl.checkoutorchestrator.repository.StepRecord;
import com.bsl.checkoutorchestrator.service.CheckoutSagaService;
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

class CheckoutSagaExecutorTest {
    private final InMemoryCheckoutSagaStore store = new InMemoryCheckoutSagaStore();
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final CheckoutSagaService sagaService = new CheckoutSagaService(store, objectMapper);
    private final CheckoutOrchestratorProperties properties = new CheckoutOrchestratorProperties();
    private final FakeDownstreamClient downstreamClient = new FakeDownstreamClient();
    private final CheckoutSagaExecutor executor = new CheckoutSagaExecutor(
        store,
        downstreamClient,
        properties,
        new TransactionTemplate(new NoOpTransactionManager()),
        objectMapper,
        Clock.fixed(Instant.parse("2026-05-08T00:00:00Z"), ZoneOffset.UTC)
    );

    @Test
    void executeDueStepsRunsCheckoutToSucceededWithPersistedIdempotencyKeys() {
        sagaService.startCheckout(checkoutRequest("checkout:worker:success"), "trace-1", "request-1");

        int executed = executor.executeDueSteps(10, "trace-1", "request-1");

        assertThat(executed).isEqualTo(4);
        Map<String, Object> view = sagaService.getCheckout(1L, "trace-2", "request-2");
        assertThat(view).containsEntry("status", "SUCCEEDED");

        assertThat(downstreamClient.calls)
            .extracting(Call::stepName)
            .containsExactly(
                CheckoutStepName.CREATE_ORDER,
                CheckoutStepName.RESERVE_STOCK,
                CheckoutStepName.AUTHORIZE_PAYMENT,
                CheckoutStepName.REQUEST_SHIPMENT
            );
        assertThat(downstreamClient.calls)
            .extracting(Call::idempotencyKey)
            .containsExactly(
                "checkout:1:CREATE_ORDER",
                "checkout:1:RESERVE_STOCK",
                "checkout:1:AUTHORIZE_PAYMENT",
                "checkout:1:REQUEST_SHIPMENT"
            );
        assertThat(downstreamClient.calls).allSatisfy(call -> {
            assertThat(call.traceId()).isEqualTo("trace-1");
            assertThat(call.requestId()).isEqualTo("request-1");
        });

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> outboxEvents = (List<Map<String, Object>>) view.get("outbox_events");
        assertThat(outboxEvents)
            .extracting(event -> event.get("event_type"))
            .contains("CHECKOUT_STARTED", "CHECKOUT_COMPLETED");
    }

    @Test
    void failedRetryingStepReusesOriginalIdempotencyKey() {
        properties.getWorker().setRetryDelayMs(0);
        downstreamClient.failFirstCreateOrder = true;
        sagaService.startCheckout(checkoutRequest("checkout:worker:retry"), "trace-1", "request-1");

        executor.executeDueSteps(1, "trace-1", "request-1");
        StepRecord failed = store.findStepById(1L).orElseThrow();
        assertThat(failed.status()).isEqualTo(CheckoutStepStatus.FAILED_RETRYING);

        executor.executeDueSteps(1, "trace-2", "request-2");

        assertThat(store.findStepById(1L).orElseThrow().status()).isEqualTo(CheckoutStepStatus.SUCCEEDED);
        assertThat(downstreamClient.calls)
            .extracting(Call::idempotencyKey)
            .containsExactly("checkout:1:CREATE_ORDER", "checkout:1:CREATE_ORDER");
    }

    @Test
    void unknownStepIsReconciledBeforeCommandRetry() {
        properties.getWorker().setRetryDelayMs(0);
        downstreamClient.timeoutFirstReserve = true;
        sagaService.startCheckout(checkoutRequest("checkout:worker:unknown"), "trace-1", "request-1");

        executor.executeDueSteps(2, "trace-1", "request-1");
        StepRecord unknown = store.findStepById(2L).orElseThrow();
        assertThat(unknown.status()).isEqualTo(CheckoutStepStatus.UNKNOWN);

        executor.executeDueSteps(1, "trace-2", "request-2");

        assertThat(store.findStepById(2L).orElseThrow().status()).isEqualTo(CheckoutStepStatus.SUCCEEDED);
        assertThat(downstreamClient.calls)
            .filteredOn(call -> call.stepName() == CheckoutStepName.RESERVE_STOCK && !call.reconcile())
            .hasSize(1);
        assertThat(downstreamClient.calls)
            .filteredOn(call -> call.stepName() == CheckoutStepName.RESERVE_STOCK && call.reconcile())
            .hasSize(1);
    }

    @Test
    void paymentFail500LeavesAuthorizeStepRetryable() {
        properties.getWorker().setRetryDelayMs(0);
        downstreamClient.failFirstPayment = true;
        sagaService.startCheckout(checkoutRequest("checkout:worker:payment-fail"), "trace-1", "request-1");

        executor.executeDueSteps(3, "trace-1", "request-1");

        StepRecord payment = store.findStepById(3L).orElseThrow();
        assertThat(payment.stepName()).isEqualTo(CheckoutStepName.AUTHORIZE_PAYMENT);
        assertThat(payment.status()).isEqualTo(CheckoutStepStatus.FAILED_RETRYING);
        assertThat(payment.idempotencyKey()).isEqualTo("checkout:1:AUTHORIZE_PAYMENT");
    }

    @Test
    void paymentSuccessButTimeoutRecoversByReconciliationWithoutSecondAuthorizeCall() {
        properties.getWorker().setRetryDelayMs(0);
        downstreamClient.paymentSuccessButTimeout = true;
        sagaService.startCheckout(checkoutRequest("checkout:worker:payment-success-timeout"), "trace-1", "request-1");

        executor.executeDueSteps(3, "trace-1", "request-1");
        assertThat(store.findStepById(3L).orElseThrow().status()).isEqualTo(CheckoutStepStatus.UNKNOWN);

        executor.executeDueSteps(2, "trace-2", "request-2");

        assertThat(store.findStepById(3L).orElseThrow().status()).isEqualTo(CheckoutStepStatus.SUCCEEDED);
        assertThat(downstreamClient.calls)
            .filteredOn(call -> call.stepName() == CheckoutStepName.AUTHORIZE_PAYMENT && !call.reconcile())
            .extracting(Call::idempotencyKey)
            .containsExactly("checkout:1:AUTHORIZE_PAYMENT");
        assertThat(downstreamClient.calls)
            .filteredOn(call -> call.stepName() == CheckoutStepName.AUTHORIZE_PAYMENT && call.reconcile())
            .extracting(Call::idempotencyKey)
            .containsExactly("checkout:1:AUTHORIZE_PAYMENT");
    }

    @Test
    void claimStepPreventsDuplicateProcessing() {
        sagaService.startCheckout(checkoutRequest("checkout:worker:claim"), "trace-1", "request-1");
        StepRecord step = store.findStepById(1L).orElseThrow();
        Instant now = Instant.parse("2026-05-08T00:00:00Z");

        assertThat(store.claimStepForProcessing(step.id(), CheckoutStepStatus.READY, now)).isEqualTo(1);
        assertThat(store.claimStepForProcessing(step.id(), CheckoutStepStatus.READY, now)).isZero();
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

    private static class FakeDownstreamClient implements CheckoutDownstreamClient {
        private final List<Call> calls = new ArrayList<>();
        private boolean failFirstCreateOrder;
        private boolean timeoutFirstReserve;
        private boolean failFirstPayment;
        private boolean paymentSuccessButTimeout;
        private int createOrderAttempts;
        private int reserveAttempts;
        private int paymentAttempts;

        @Override
        public Map<String, Object> execute(
            CheckoutStepName stepName,
            Map<String, Object> request,
            String idempotencyKey,
            String traceId,
            String requestId
        ) {
            calls.add(new Call(stepName, idempotencyKey, traceId, requestId, false));
            if (stepName == CheckoutStepName.CREATE_ORDER && failFirstCreateOrder && createOrderAttempts++ == 0) {
                throw new DownstreamCallException("downstream_http_500", "order-service failed", false, true);
            }
            if (stepName == CheckoutStepName.RESERVE_STOCK && timeoutFirstReserve && reserveAttempts++ == 0) {
                throw new DownstreamCallException("downstream_timeout", "inventory timeout", true, true);
            }
            if (stepName == CheckoutStepName.AUTHORIZE_PAYMENT && failFirstPayment && paymentAttempts++ == 0) {
                throw new DownstreamCallException("downstream_http_500", "payment-service failed", false, true);
            }
            if (stepName == CheckoutStepName.AUTHORIZE_PAYMENT && paymentSuccessButTimeout && paymentAttempts++ == 0) {
                throw new DownstreamCallException("downstream_timeout", "payment response timeout after success", true, true);
            }
            return success(stepName);
        }

        @Override
        public Optional<Map<String, Object>> reconcile(
            CheckoutStepName stepName,
            String idempotencyKey,
            String traceId,
            String requestId
        ) {
            calls.add(new Call(stepName, idempotencyKey, traceId, requestId, true));
            return Optional.of(success(stepName));
        }

        @Override
        public Map<String, Object> compensate(
            CheckoutStepName stepName,
            Map<String, Object> request,
            String idempotencyKey,
            String traceId,
            String requestId
        ) {
            calls.add(new Call(stepName, idempotencyKey, traceId, requestId, false));
            return Map.of("status", "COMPENSATED", "step_name", stepName.name());
        }

        private Map<String, Object> success(CheckoutStepName stepName) {
            return switch (stepName) {
                case CREATE_ORDER -> Map.of("order_id", "ord-1", "status", "PENDING");
                case RESERVE_STOCK -> Map.of("reservation_id", "inv-res-1", "status", "RESERVED");
                case AUTHORIZE_PAYMENT -> Map.of("payment_id", "pay-1", "pg_transaction_id", "pg-1", "status", "AUTHORIZED");
                case REQUEST_SHIPMENT -> Map.of("shipment_id", "ship-1", "status", "REQUESTED");
            };
        }
    }

    private record Call(
        CheckoutStepName stepName,
        String idempotencyKey,
        String traceId,
        String requestId,
        boolean reconcile
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
