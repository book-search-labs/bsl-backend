package com.bsl.payment.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.bsl.payment.common.ApiException;
import com.bsl.payment.repository.IdempotencyRecord;
import com.bsl.payment.repository.PaymentStore;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class PaymentServiceTest {
    private final InMemoryPaymentStore store = new InMemoryPaymentStore();
    private final FailureModeService failureModeService = new FailureModeService();
    private final PaymentService service = new PaymentService(store, new ObjectMapper(), failureModeService);

    @Test
    void duplicateAuthorizeReplaysSamePaymentWithoutDuplicateRows() {
        Map<String, Object> first = service.authorize(authorizeRequest(), "checkout:1:AUTHORIZE_PAYMENT", "trace-1", "request-1");
        Map<String, Object> second = service.authorize(authorizeRequest(), "checkout:1:AUTHORIZE_PAYMENT", "trace-2", "request-2");

        assertThat(second.get("payment_id")).isEqualTo(first.get("payment_id"));
        assertThat(store.authorizations).hasSize(1);
    }

    @Test
    void sameKeyCannotBeReusedForCancelOperation() {
        service.authorize(authorizeRequest(), "checkout:1:AUTHORIZE_PAYMENT", "trace-1", "request-1");

        assertThatThrownBy(() -> service.cancel(cancelRequest("pay-1"), "checkout:1:AUTHORIZE_PAYMENT", "trace-1", "request-1"))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("operation");
    }

    @Test
    void duplicateCancelReplaysSameCancellation() {
        Map<String, Object> first = service.cancel(cancelRequest("pay-1"), "checkout:1:AUTHORIZE_PAYMENT:compensate", "trace-1", "request-1");
        Map<String, Object> second = service.cancel(cancelRequest("pay-1"), "checkout:1:AUTHORIZE_PAYMENT:compensate", "trace-2", "request-2");

        assertThat(second.get("cancellation_id")).isEqualTo(first.get("cancellation_id"));
        assertThat(store.cancellations).hasSize(1);
    }

    @Test
    void fail500FailureModeDoesNotCreatePaymentSideEffect() {
        failureModeService.setMode("FAIL_500");

        assertThatThrownBy(() -> service.authorize(authorizeRequest(), "checkout:1:AUTHORIZE_PAYMENT", "trace-1", "request-1"))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("FAIL_500");
        assertThat(store.authorizations).isEmpty();
        assertThat(store.idempotency).isEmpty();
    }

    @Test
    void successButTimeoutModePersistsResultAndDuplicateRequestReplaysIt() {
        failureModeService.setMode("SUCCESS_BUT_TIMEOUT");
        Map<String, Object> first = service.authorize(authorizeRequest(), "checkout:1:AUTHORIZE_PAYMENT", "trace-1", "request-1");

        Map<String, Object> second = service.authorize(authorizeRequest(), "checkout:1:AUTHORIZE_PAYMENT", "trace-2", "request-2");

        assertThat(second.get("payment_id")).isEqualTo(first.get("payment_id"));
        assertThat(store.authorizations).hasSize(1);
    }

    private Map<String, Object> authorizeRequest() {
        return Map.of(
            "checkout_id", 1,
            "order_id", "ord-1",
            "amount", 12000,
            "currency", "KRW",
            "method", "MOCK"
        );
    }

    private Map<String, Object> cancelRequest(String paymentId) {
        return Map.of(
            "checkout_id", 1,
            "payment_id", paymentId,
            "reason", "compensation"
        );
    }

    private static class InMemoryPaymentStore implements PaymentStore {
        private final Map<String, IdempotencyRecord> idempotency = new LinkedHashMap<>();
        private final Map<String, Map<String, Object>> authorizations = new LinkedHashMap<>();
        private final Map<String, Map<String, Object>> cancellations = new LinkedHashMap<>();

        @Override
        public Optional<IdempotencyRecord> findIdempotency(String idempotencyKey) {
            return Optional.ofNullable(idempotency.get(idempotencyKey));
        }

        @Override
        public void insertIdempotency(String idempotencyKey, String operationType, String requestHash, String status) {
            idempotency.put(idempotencyKey, new IdempotencyRecord(idempotencyKey, operationType, requestHash, status, null, null));
        }

        @Override
        public void updateIdempotencySucceeded(String idempotencyKey, String responsePayload) {
            IdempotencyRecord existing = idempotency.get(idempotencyKey);
            idempotency.put(idempotencyKey, new IdempotencyRecord(
                existing.idempotencyKey(),
                existing.operationType(),
                existing.requestHash(),
                "SUCCEEDED",
                responsePayload,
                null
            ));
        }

        @Override
        public void insertAuthorization(
            String paymentId,
            long checkoutId,
            String orderId,
            BigDecimal amount,
            String currency,
            String status,
            String idempotencyKey,
            String pgTransactionId,
            String responsePayload
        ) {
            authorizations.put(paymentId, Map.of("payment_id", paymentId, "status", status, "idempotency_key", idempotencyKey));
        }

        @Override
        public void insertCancellation(
            String cancellationId,
            String paymentId,
            long checkoutId,
            String status,
            String idempotencyKey,
            String responsePayload
        ) {
            cancellations.put(cancellationId, Map.of("cancellation_id", cancellationId, "payment_id", paymentId, "status", status));
        }
    }
}
