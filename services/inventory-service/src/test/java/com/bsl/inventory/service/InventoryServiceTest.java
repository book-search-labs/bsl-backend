package com.bsl.inventory.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.bsl.inventory.common.ApiException;
import com.bsl.inventory.repository.IdempotencyRecord;
import com.bsl.inventory.repository.InventoryStore;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class InventoryServiceTest {
    private final InMemoryInventoryStore store = new InMemoryInventoryStore();
    private final InventoryService service = new InventoryService(store, new ObjectMapper());

    @Test
    void duplicateReserveReplaysSameReservationWithoutDoubleDecrement() {
        store.stock.put("book-1", new Stock(3, 0));

        Map<String, Object> first = service.reserve(reserveRequest(2), "checkout:1:RESERVE_STOCK", "trace-1", "request-1");
        Map<String, Object> second = service.reserve(reserveRequest(2), "checkout:1:RESERVE_STOCK", "trace-2", "request-2");

        assertThat(second.get("reservation_id")).isEqualTo(first.get("reservation_id"));
        assertThat(store.stock.get("book-1").available).isEqualTo(1);
        assertThat(store.stock.get("book-1").reserved).isEqualTo(2);
        assertThat(store.reservations).hasSize(1);
    }

    @Test
    void insufficientStockFailsBeforeReservationIsCreated() {
        store.stock.put("book-1", new Stock(1, 0));

        assertThatThrownBy(() -> service.reserve(reserveRequest(2), "checkout:1:RESERVE_STOCK", "trace-1", "request-1"))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("재고");
        assertThat(store.reservations).isEmpty();
    }

    @Test
    void duplicateReleaseDoesNotReleaseStockTwice() {
        store.stock.put("book-1", new Stock(3, 0));
        Map<String, Object> reserve = service.reserve(reserveRequest(2), "checkout:1:RESERVE_STOCK", "trace-1", "request-1");

        service.release(releaseRequest(reserve.get("reservation_id").toString()), "checkout:1:RESERVE_STOCK:compensate", "trace-1", "request-1");
        service.release(releaseRequest(reserve.get("reservation_id").toString()), "checkout:1:RESERVE_STOCK:compensate", "trace-2", "request-2");

        assertThat(store.stock.get("book-1").available).isEqualTo(3);
        assertThat(store.stock.get("book-1").reserved).isEqualTo(0);
    }

    private Map<String, Object> reserveRequest(int quantity) {
        return Map.of(
            "checkout_id", 1,
            "order_id", "ord-1",
            "items", List.of(Map.of("book_id", "book-1", "quantity", quantity))
        );
    }

    private Map<String, Object> releaseRequest(String reservationId) {
        return Map.of(
            "checkout_id", 1,
            "reservation_id", reservationId,
            "reason", "compensation"
        );
    }

    private static class InMemoryInventoryStore implements InventoryStore {
        private final Map<String, IdempotencyRecord> idempotency = new LinkedHashMap<>();
        private final Map<String, Stock> stock = new LinkedHashMap<>();
        private final Map<String, Map<String, Object>> reservations = new LinkedHashMap<>();
        private final Map<String, List<Map<String, Object>>> lines = new LinkedHashMap<>();

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
        public int reserveStock(String bookId, int quantity) {
            Stock row = stock.get(bookId);
            if (row == null || row.available < quantity) {
                return 0;
            }
            row.available -= quantity;
            row.reserved += quantity;
            return 1;
        }

        @Override
        public int releaseStock(String bookId, int quantity) {
            Stock row = stock.get(bookId);
            if (row == null || row.reserved < quantity) {
                return 0;
            }
            row.available += quantity;
            row.reserved -= quantity;
            return 1;
        }

        @Override
        public void insertReservation(String reservationId, long checkoutId, String orderId, String status, String idempotencyKey, String responsePayload) {
            reservations.put(reservationId, new LinkedHashMap<>(Map.of(
                "reservation_id", reservationId,
                "checkout_id", checkoutId,
                "order_id", orderId,
                "status", status
            )));
        }

        @Override
        public void insertReservationLine(String reservationId, String bookId, int quantity) {
            lines.computeIfAbsent(reservationId, ignored -> new ArrayList<>()).add(Map.of("book_id", bookId, "quantity", quantity));
        }

        @Override
        public Optional<Map<String, Object>> findReservation(String reservationId) {
            return Optional.ofNullable(reservations.get(reservationId));
        }

        @Override
        public List<Map<String, Object>> findReservationLines(String reservationId) {
            return List.copyOf(lines.getOrDefault(reservationId, List.of()));
        }

        @Override
        public int markReservationReleased(String reservationId) {
            Map<String, Object> reservation = reservations.get(reservationId);
            if (reservation == null || !"RESERVED".equals(reservation.get("status"))) {
                return 0;
            }
            reservation.put("status", "RELEASED");
            return 1;
        }
    }

    private static class Stock {
        private int available;
        private int reserved;

        private Stock(int available, int reserved) {
            this.available = available;
            this.reserved = reserved;
        }
    }
}
