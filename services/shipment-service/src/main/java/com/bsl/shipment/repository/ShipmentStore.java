package com.bsl.shipment.repository;

import java.util.Map;
import java.util.Optional;

public interface ShipmentStore {
    Optional<IdempotencyRecord> findIdempotency(String idempotencyKey);

    void insertIdempotency(String idempotencyKey, String operationType, String requestHash, String status);

    void updateIdempotencySucceeded(String idempotencyKey, String responsePayload);

    void insertShipment(String shipmentId, long checkoutId, String orderId, String status, String idempotencyKey, String address, String responsePayload);

    Optional<Map<String, Object>> findShipment(String shipmentId);

    int markShipmentCancelled(String shipmentId);
}

