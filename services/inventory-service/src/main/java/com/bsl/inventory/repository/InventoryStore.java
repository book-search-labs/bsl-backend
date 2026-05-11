package com.bsl.inventory.repository;

import java.util.List;
import java.util.Map;
import java.util.Optional;

public interface InventoryStore {
    Optional<IdempotencyRecord> findIdempotency(String idempotencyKey);

    void insertIdempotency(String idempotencyKey, String operationType, String requestHash, String status);

    void updateIdempotencySucceeded(String idempotencyKey, String responsePayload);

    int reserveStock(String bookId, int quantity);

    int releaseStock(String bookId, int quantity);

    void insertReservation(String reservationId, long checkoutId, String orderId, String status, String idempotencyKey, String responsePayload);

    void insertReservationLine(String reservationId, String bookId, int quantity);

    Optional<Map<String, Object>> findReservation(String reservationId);

    List<Map<String, Object>> findReservationLines(String reservationId);

    int markReservationReleased(String reservationId);
}

