package com.bsl.refund.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.bsl.refund.client.DownstreamCallException;
import com.bsl.refund.client.RefundDownstreamClient;
import com.bsl.refund.common.ApiException;
import com.bsl.refund.repository.IdempotencyRecord;
import com.bsl.refund.repository.RefundItem;
import com.bsl.refund.repository.RefundRecord;
import com.bsl.refund.repository.RefundStore;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class RefundServiceTest {
    private final InMemoryRefundStore store = new InMemoryRefundStore();
    private final FakeRefundDownstreamClient downstreamClient = new FakeRefundDownstreamClient();
    private final RefundService service = new RefundService(store, downstreamClient, new ObjectMapper());

    @Test
    void createAndGetRefund() {
        Map<String, Object> created = service.create(refundRequest(), "refund:create:1", "trace-1", "request-1");

        Map<String, Object> found = service.get(created.get("refund_id").toString(), "trace-1", "request-2");

        assertThat(found.get("status")).isEqualTo("REQUESTED");
        assertThat(found.get("order_id")).isEqualTo("ord-1");
        assertThat(store.events).hasSize(1);
        assertThat(store.outboxEvents).hasSize(1);
    }

    @Test
    void approveAndProcessCancelsPaymentAndReleasesInventory() {
        String refundId = createApprovedRefund();

        Map<String, Object> processed = service.process(refundId, Map.of(), "refund:process:1", "trace-1", "request-3");

        assertThat(processed.get("status")).isEqualTo("COMPLETED");
        assertThat(downstreamClient.paymentCancelCalls).isEqualTo(1);
        assertThat(downstreamClient.inventoryReleaseCalls).isEqualTo(1);
        assertThat(store.findRefund(refundId).orElseThrow().status()).isEqualTo("COMPLETED");
    }

    @Test
    void duplicateProcessReplaysWithoutDoublePaymentOrInventorySideEffects() {
        String refundId = createApprovedRefund();

        Map<String, Object> first = service.process(refundId, Map.of(), "refund:process:1", "trace-1", "request-3");
        Map<String, Object> second = service.process(refundId, Map.of(), "refund:process:1", "trace-2", "request-4");

        assertThat(second.get("status")).isEqualTo(first.get("status"));
        assertThat(downstreamClient.paymentCancelCalls).isEqualTo(1);
        assertThat(downstreamClient.inventoryReleaseCalls).isEqualTo(1);
    }

    @Test
    void paymentFailureLeavesRefundRetryable() {
        String refundId = createApprovedRefund();
        downstreamClient.failPayment = true;

        assertThatThrownBy(() -> service.process(refundId, Map.of(), "refund:process:1", "trace-1", "request-3"))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("payment failed");

        assertThat(store.findRefund(refundId).orElseThrow().status()).isEqualTo("FAILED_RETRYING");
        assertThat(downstreamClient.inventoryReleaseCalls).isZero();
    }

    @Test
    void paymentSuccessButTimeoutRecoversByIdempotencyLookupWithoutSecondCancel() {
        String refundId = createApprovedRefund();
        downstreamClient.paymentSuccessButTimeout = true;

        Map<String, Object> processed = service.process(refundId, Map.of(), "refund:process:1", "trace-1", "request-3");

        assertThat(processed.get("status")).isEqualTo("COMPLETED");
        assertThat(downstreamClient.paymentCancelCalls).isEqualTo(1);
        assertThat(downstreamClient.paymentLookupCalls).isEqualTo(1);
        assertThat(store.findRefund(refundId).orElseThrow().status()).isEqualTo("COMPLETED");
    }

    @Test
    void paymentTimeoutWithoutStoredResultReturnsFullUnknownRefundState() {
        String refundId = createApprovedRefund();
        downstreamClient.paymentTimeoutWithoutResult = true;

        Map<String, Object> processed = service.process(refundId, Map.of(), "refund:process:1", "trace-1", "request-3");

        assertThat(processed)
            .containsEntry("status", "UNKNOWN")
            .containsEntry("order_id", "ord-1")
            .containsEntry("checkout_id", 1L)
            .containsEntry("amount", BigDecimal.valueOf(1000.0))
            .containsEntry("currency", "KRW")
            .containsEntry("error_code", "payment_cancel_unknown");
        assertThat(processed.get("items")).asList().hasSize(1);
        assertThat(store.findRefund(refundId).orElseThrow().status()).isEqualTo("UNKNOWN");
    }

    @Test
    void sameIdempotencyKeyWithDifferentPayloadIsRejected() {
        service.create(refundRequest(), "refund:create:1", "trace-1", "request-1");
        Map<String, Object> changed = new LinkedHashMap<>(refundRequest());
        changed.put("amount", 2000);

        assertThatThrownBy(() -> service.create(changed, "refund:create:1", "trace-1", "request-2"))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("payload");
    }

    private String createApprovedRefund() {
        String refundId = service.create(refundRequest(), "refund:create:" + store.refunds.size(), "trace-1", "request-1")
            .get("refund_id")
            .toString();
        service.approve(refundId, Map.of(), "refund:approve:" + refundId, "trace-1", "request-2");
        return refundId;
    }

    private Map<String, Object> refundRequest() {
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("order_id", "ord-1");
        request.put("checkout_id", 1);
        request.put("user_id", "user-1");
        request.put("payment_id", "pay-1");
        request.put("inventory_reservation_id", "inv-res-1");
        request.put("reason", "DAMAGED_BOOK");
        request.put("amount", 1000);
        request.put("currency", "KRW");
        request.put("items", List.of(Map.of("book_id", "book-1", "quantity", 1, "amount", 1000)));
        return request;
    }

    private static class FakeRefundDownstreamClient implements RefundDownstreamClient {
        private final Map<String, Map<String, Object>> paymentByKey = new LinkedHashMap<>();
        private final Map<String, Map<String, Object>> inventoryByKey = new LinkedHashMap<>();
        private int paymentCancelCalls;
        private int paymentLookupCalls;
        private int inventoryReleaseCalls;
        private boolean failPayment;
        private boolean paymentSuccessButTimeout;
        private boolean paymentTimeoutWithoutResult;

        @Override
        public Map<String, Object> cancelPayment(
            Map<String, Object> request,
            String idempotencyKey,
            String traceId,
            String requestId
        ) {
            paymentCancelCalls++;
            if (failPayment) {
                throw new DownstreamCallException("payment failed", false);
            }
            if (paymentTimeoutWithoutResult) {
                throw new DownstreamCallException("payment timeout", true);
            }
            Map<String, Object> response = Map.of(
                "cancellation_id", "pay-cancel-1",
                "payment_id", request.get("payment_id"),
                "status", "CANCELLED"
            );
            paymentByKey.put(idempotencyKey, response);
            if (paymentSuccessButTimeout) {
                throw new DownstreamCallException("payment timeout", true);
            }
            return response;
        }

        @Override
        public Optional<Map<String, Object>> findPaymentByIdempotencyKey(String idempotencyKey, String traceId, String requestId) {
            paymentLookupCalls++;
            return Optional.ofNullable(paymentByKey.get(idempotencyKey));
        }

        @Override
        public Map<String, Object> releaseInventory(
            Map<String, Object> request,
            String idempotencyKey,
            String traceId,
            String requestId
        ) {
            inventoryReleaseCalls++;
            Map<String, Object> response = Map.of(
                "reservation_id", request.get("reservation_id"),
                "status", "RELEASED"
            );
            inventoryByKey.put(idempotencyKey, response);
            return response;
        }

        @Override
        public Optional<Map<String, Object>> findInventoryByIdempotencyKey(String idempotencyKey, String traceId, String requestId) {
            return Optional.ofNullable(inventoryByKey.get(idempotencyKey));
        }
    }

    private static class InMemoryRefundStore implements RefundStore {
        private final Map<String, IdempotencyRecord> idempotency = new LinkedHashMap<>();
        private final Map<String, RefundRecord> refunds = new LinkedHashMap<>();
        private final Map<String, List<RefundItem>> items = new LinkedHashMap<>();
        private final List<Map<String, Object>> events = new ArrayList<>();
        private final List<Map<String, Object>> outboxEvents = new ArrayList<>();

        @Override
        public Optional<IdempotencyRecord> findIdempotency(String idempotencyKey) {
            return Optional.ofNullable(idempotency.get(idempotencyKey));
        }

        @Override
        public void insertIdempotency(String idempotencyKey, String operationType, String requestHash, String status) {
            idempotency.put(idempotencyKey, new IdempotencyRecord(idempotencyKey, operationType, requestHash, status, null, null));
        }

        @Override
        public void markIdempotencyProcessing(String idempotencyKey) {
            IdempotencyRecord existing = idempotency.get(idempotencyKey);
            idempotency.put(idempotencyKey, new IdempotencyRecord(
                existing.idempotencyKey(),
                existing.operationType(),
                existing.requestHash(),
                "PROCESSING",
                existing.responsePayload(),
                null
            ));
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
        public void updateIdempotencyFailed(String idempotencyKey, String errorMessage) {
            IdempotencyRecord existing = idempotency.get(idempotencyKey);
            idempotency.put(idempotencyKey, new IdempotencyRecord(
                existing.idempotencyKey(),
                existing.operationType(),
                existing.requestHash(),
                "FAILED",
                existing.responsePayload(),
                errorMessage
            ));
        }

        @Override
        public void insertRefund(
            String refundId,
            String orderId,
            long checkoutId,
            String userId,
            String paymentId,
            String inventoryReservationId,
            String status,
            String reason,
            BigDecimal totalAmount,
            String currency,
            String requestPayload,
            String responsePayload
        ) {
            refunds.put(refundId, new RefundRecord(
                refunds.size() + 1L,
                refundId,
                orderId,
                checkoutId,
                userId,
                paymentId,
                inventoryReservationId,
                status,
                reason,
                totalAmount,
                currency,
                requestPayload,
                responsePayload,
                null
            ));
        }

        @Override
        public void insertRefundItem(String refundId, String bookId, int quantity, BigDecimal amount) {
            items.computeIfAbsent(refundId, ignored -> new ArrayList<>())
                .add(new RefundItem(refundId, bookId, quantity, amount));
        }

        @Override
        public Optional<RefundRecord> findRefund(String refundId) {
            return Optional.ofNullable(refunds.get(refundId));
        }

        @Override
        public List<RefundRecord> findRefundsByOrderId(String orderId) {
            return refunds.values().stream().filter(refund -> refund.orderId().equals(orderId)).toList();
        }

        @Override
        public List<RefundRecord> findAllRefunds() {
            return List.copyOf(refunds.values());
        }

        @Override
        public List<RefundItem> findRefundItems(String refundId) {
            return items.getOrDefault(refundId, List.of());
        }

        @Override
        public void updateRefundStatus(String refundId, String status, String responsePayload, String errorMessage) {
            RefundRecord existing = refunds.get(refundId);
            refunds.put(refundId, new RefundRecord(
                existing.id(),
                existing.refundId(),
                existing.orderId(),
                existing.checkoutId(),
                existing.userId(),
                existing.paymentId(),
                existing.inventoryReservationId(),
                status,
                existing.reason(),
                existing.totalAmount(),
                existing.currency(),
                existing.requestPayload(),
                responsePayload,
                errorMessage
            ));
        }

        @Override
        public void insertRefundEvent(String refundId, String eventType, String payload) {
            events.add(Map.of("refund_id", refundId, "event_type", eventType));
        }

        @Override
        public void insertOutboxEvent(String aggregateId, String eventType, String eventKey, String payload) {
            outboxEvents.add(Map.of("aggregate_id", aggregateId, "event_type", eventType, "event_key", eventKey));
        }
    }
}
