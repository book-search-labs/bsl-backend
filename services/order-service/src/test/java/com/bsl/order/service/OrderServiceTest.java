package com.bsl.order.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.bsl.order.common.ApiException;
import com.bsl.order.repository.IdempotencyRecord;
import com.bsl.order.repository.OrderStore;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class OrderServiceTest {
    private final InMemoryOrderStore store = new InMemoryOrderStore();
    private final OrderService service = new OrderService(store, new ObjectMapper());

    @Test
    void duplicateIdempotencyKeyReplaysSameOrderWithoutDuplicateRows() {
        Map<String, Object> first = service.createOrder(orderRequest(1), "checkout:1:CREATE_ORDER", "trace-1", "request-1");
        Map<String, Object> second = service.createOrder(orderRequest(1), "checkout:1:CREATE_ORDER", "trace-2", "request-2");

        assertThat(second.get("order_id")).isEqualTo(first.get("order_id"));
        assertThat(store.orders).hasSize(1);
        assertThat(store.lines.get(first.get("order_id"))).hasSize(1);
    }

    @Test
    void sameKeyWithDifferentPayloadConflicts() {
        service.createOrder(orderRequest(1), "checkout:1:CREATE_ORDER", "trace-1", "request-1");

        assertThatThrownBy(() -> service.createOrder(orderRequest(2), "checkout:1:CREATE_ORDER", "trace-1", "request-1"))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("payload");
    }

    @Test
    void missingIdempotencyKeyIsRejected() {
        assertThatThrownBy(() -> service.createOrder(orderRequest(1), null, "trace-1", "request-1"))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("Idempotency-Key");
    }

    private Map<String, Object> orderRequest(long checkoutId) {
        return Map.of(
            "checkout_id", checkoutId,
            "user_id", "101",
            "items", List.of(Map.of("book_id", "book-1", "title", "Book", "quantity", 1, "unit_price", 12000)),
            "total_amount", 12000,
            "currency", "KRW"
        );
    }

    private static class InMemoryOrderStore implements OrderStore {
        private final Map<String, IdempotencyRecord> idempotency = new LinkedHashMap<>();
        private final Map<String, Map<String, Object>> orders = new LinkedHashMap<>();
        private final Map<Object, List<Map<String, Object>>> lines = new LinkedHashMap<>();

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
        public void insertOrder(String orderId, String userId, long checkoutId, String status, BigDecimal totalAmount, String currency) {
            orders.put(orderId, Map.of(
                "order_id", orderId,
                "user_id", userId,
                "checkout_id", checkoutId,
                "status", status,
                "total_amount", totalAmount,
                "currency", currency
            ));
        }

        @Override
        public void insertOrderLine(String orderId, String bookId, String title, int quantity, BigDecimal unitPrice) {
            lines.computeIfAbsent(orderId, ignored -> new ArrayList<>()).add(Map.of(
                "book_id", bookId,
                "title", title,
                "quantity", quantity,
                "unit_price", unitPrice
            ));
        }

        @Override
        public Optional<Map<String, Object>> findOrder(String orderId) {
            return Optional.ofNullable(orders.get(orderId));
        }

        @Override
        public List<Map<String, Object>> findOrderLines(String orderId) {
            return List.copyOf(lines.getOrDefault(orderId, List.of()));
        }
    }
}
