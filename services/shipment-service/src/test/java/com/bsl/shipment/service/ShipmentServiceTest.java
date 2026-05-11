package com.bsl.shipment.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.bsl.shipment.common.ApiException;
import com.bsl.shipment.repository.IdempotencyRecord;
import com.bsl.shipment.repository.ShipmentStore;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class ShipmentServiceTest {
    private final InMemoryShipmentStore store = new InMemoryShipmentStore();
    private final ShipmentService service = new ShipmentService(store, new ObjectMapper());

    @Test
    void duplicateCreateReplaysSameShipmentWithoutDuplicateRows() {
        Map<String, Object> first = service.create(createRequest(), "checkout:1:REQUEST_SHIPMENT", "trace-1", "request-1");
        Map<String, Object> second = service.create(createRequest(), "checkout:1:REQUEST_SHIPMENT", "trace-2", "request-2");

        assertThat(second.get("shipment_id")).isEqualTo(first.get("shipment_id"));
        assertThat(store.shipments).hasSize(1);
    }

    @Test
    void duplicateCancelReplaysSameResult() {
        Map<String, Object> create = service.create(createRequest(), "checkout:1:REQUEST_SHIPMENT", "trace-1", "request-1");

        Map<String, Object> first = service.cancel(cancelRequest(create.get("shipment_id").toString()), "checkout:1:REQUEST_SHIPMENT:compensate", "trace-1", "request-1");
        Map<String, Object> second = service.cancel(cancelRequest(create.get("shipment_id").toString()), "checkout:1:REQUEST_SHIPMENT:compensate", "trace-2", "request-2");

        assertThat(second.get("shipment_id")).isEqualTo(first.get("shipment_id"));
        assertThat(store.shipments.get(create.get("shipment_id")).get("status")).isEqualTo("CANCELLED");
    }

    @Test
    void sameKeyWithDifferentPayloadConflicts() {
        service.create(createRequest(), "checkout:1:REQUEST_SHIPMENT", "trace-1", "request-1");

        assertThatThrownBy(() -> service.create(createRequest("ord-2"), "checkout:1:REQUEST_SHIPMENT", "trace-1", "request-1"))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("payload");
    }

    private Map<String, Object> createRequest() {
        return createRequest("ord-1");
    }

    private Map<String, Object> createRequest(String orderId) {
        return Map.of(
            "checkout_id", 1,
            "order_id", orderId,
            "shipping_address", Map.of("recipient", "tester", "line1", "Seoul"),
            "items", List.of(Map.of("book_id", "book-1", "quantity", 1))
        );
    }

    private Map<String, Object> cancelRequest(String shipmentId) {
        return Map.of(
            "checkout_id", 1,
            "shipment_id", shipmentId,
            "reason", "compensation"
        );
    }

    private static class InMemoryShipmentStore implements ShipmentStore {
        private final Map<String, IdempotencyRecord> idempotency = new LinkedHashMap<>();
        private final Map<String, Map<String, Object>> shipments = new LinkedHashMap<>();

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
        public void insertShipment(String shipmentId, long checkoutId, String orderId, String status, String idempotencyKey, String address, String responsePayload) {
            shipments.put(shipmentId, new LinkedHashMap<>(Map.of(
                "shipment_id", shipmentId,
                "checkout_id", checkoutId,
                "order_id", orderId,
                "status", status,
                "address", address
            )));
        }

        @Override
        public Optional<Map<String, Object>> findShipment(String shipmentId) {
            return Optional.ofNullable(shipments.get(shipmentId));
        }

        @Override
        public int markShipmentCancelled(String shipmentId) {
            Map<String, Object> shipment = shipments.get(shipmentId);
            if (shipment == null || !"REQUESTED".equals(shipment.get("status"))) {
                return 0;
            }
            shipment.put("status", "CANCELLED");
            return 1;
        }
    }
}
