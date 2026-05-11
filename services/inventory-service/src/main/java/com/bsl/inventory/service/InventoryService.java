package com.bsl.inventory.service;

import com.bsl.inventory.common.ApiException;
import com.bsl.inventory.common.ResponseSupport;
import com.bsl.inventory.repository.IdempotencyRecord;
import com.bsl.inventory.repository.InventoryStore;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    private static final String SERVICE_NAME = "inventory-service";
    private static final String RESERVE_STOCK = "RESERVE_STOCK";
    private static final String RELEASE_STOCK = "RELEASE_STOCK";
    private static final String PROCESSING = "PROCESSING";

    private final InventoryStore store;
    private final ObjectMapper objectMapper;
    private final FailureModeService failureModeService;

    @Autowired
    public InventoryService(InventoryStore store, ObjectMapper objectMapper, FailureModeService failureModeService) {
        this.store = store;
        this.objectMapper = objectMapper.copy().configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true);
        this.failureModeService = failureModeService;
    }

    InventoryService(InventoryStore store, ObjectMapper objectMapper) {
        this(store, objectMapper, new FailureModeService());
    }

    @Transactional
    public Map<String, Object> reserve(Map<String, Object> request, String idempotencyKey, String traceId, String requestId) {
        return executeIdempotent(RESERVE_STOCK, request, idempotencyKey, () -> createReservation(request, idempotencyKey, traceId, requestId));
    }

    @Transactional
    public Map<String, Object> release(Map<String, Object> request, String idempotencyKey, String traceId, String requestId) {
        return executeIdempotent(RELEASE_STOCK, request, idempotencyKey, () -> releaseReservation(request, traceId, requestId));
    }

    @Transactional(readOnly = true)
    public Map<String, Object> findByIdempotencyKey(String idempotencyKey) {
        IdempotencyRecord record = store.findIdempotency(idempotencyKey)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "idempotency_not_found", "Idempotency-Key 결과를 찾을 수 없습니다."));
        if (record.responsePayload() == null || record.responsePayload().isBlank()) {
            throw new ApiException(HttpStatus.CONFLICT, "idempotency_in_progress", "동일 Idempotency-Key 요청이 처리 중입니다.");
        }
        return readJson(record.responsePayload());
    }

    private Map<String, Object> executeIdempotent(String operationType, Map<String, Object> request, String idempotencyKey, Command command) {
        requireIdempotencyKey(idempotencyKey);
        Map<String, Object> payload = normalize(request);
        String requestHash = hash(payload);
        IdempotencyRecord existing = store.findIdempotency(idempotencyKey).orElse(null);
        if (existing != null) {
            return replay(existing, operationType, requestHash);
        }
        FailureMode selectedMode = failureModeService.beforeSideEffect();
        try {
            store.insertIdempotency(idempotencyKey, operationType, requestHash, PROCESSING);
        } catch (DuplicateKeyException ex) {
            return replay(store.findIdempotency(idempotencyKey).orElseThrow(() -> ex), operationType, requestHash);
        }
        Map<String, Object> response = command.execute();
        store.updateIdempotencySucceeded(idempotencyKey, writeJson(response));
        failureModeService.afterSideEffect(selectedMode);
        return response;
    }

    private Map<String, Object> createReservation(Map<String, Object> request, String idempotencyKey, String traceId, String requestId) {
        Map<String, Object> payload = normalize(request);
        long checkoutId = requiredLong(payload, "checkout_id");
        String orderId = requiredString(payload, "order_id");
        List<Map<String, Object>> items = requiredList(payload, "items");
        String reservationId = "inv-res-" + UUID.randomUUID();

        for (Map<String, Object> item : items) {
            String bookId = requiredString(item, "book_id");
            int quantity = requiredInt(item, "quantity");
            if (store.reserveStock(bookId, quantity) != 1) {
                throw new ApiException(HttpStatus.CONFLICT, "stock_insufficient", "재고가 부족합니다: " + bookId);
            }
        }

        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.put("reservation_id", reservationId);
        response.put("checkout_id", checkoutId);
        response.put("order_id", orderId);
        response.put("status", "RESERVED");
        response.put("items", items);

        store.insertReservation(reservationId, checkoutId, orderId, "RESERVED", idempotencyKey, writeJson(response));
        for (Map<String, Object> item : items) {
            store.insertReservationLine(reservationId, requiredString(item, "book_id"), requiredInt(item, "quantity"));
        }
        return response;
    }

    private Map<String, Object> releaseReservation(Map<String, Object> request, String traceId, String requestId) {
        Map<String, Object> payload = normalize(request);
        long checkoutId = requiredLong(payload, "checkout_id");
        String reservationId = requiredString(payload, "reservation_id");
        requiredString(payload, "reason");
        Map<String, Object> reservation = store.findReservation(reservationId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "reservation_not_found", "재고 예약을 찾을 수 없습니다."));
        List<Map<String, Object>> lines = store.findReservationLines(reservationId);
        if (store.markReservationReleased(reservationId) == 1) {
            for (Map<String, Object> line : lines) {
                int updated = store.releaseStock(line.get("book_id").toString(), number(line.get("quantity")).intValue());
                if (updated != 1) {
                    throw new ApiException(HttpStatus.CONFLICT, "stock_release_failed", "재고 예약 해제에 실패했습니다.");
                }
            }
        }

        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.put("reservation_id", reservationId);
        response.put("checkout_id", checkoutId);
        response.put("order_id", reservation.get("order_id"));
        response.put("status", "RELEASED");
        response.put("items", lines);
        return response;
    }

    private Map<String, Object> replay(IdempotencyRecord existing, String operationType, String requestHash) {
        if (!existing.operationType().equals(operationType)) {
            throw new ApiException(HttpStatus.CONFLICT, "idempotency_key_reused", "Idempotency-Key가 다른 operation에 재사용되었습니다.");
        }
        if (!existing.requestHash().equals(requestHash)) {
            throw new ApiException(HttpStatus.CONFLICT, "idempotency_payload_mismatch", "Idempotency-Key payload가 최초 요청과 다릅니다.");
        }
        if (PROCESSING.equals(existing.status())) {
            throw new ApiException(HttpStatus.CONFLICT, "idempotency_in_progress", "동일 Idempotency-Key 요청이 처리 중입니다.");
        }
        return readJson(existing.responsePayload());
    }

    private void requireIdempotencyKey(String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "missing_idempotency_key", "Idempotency-Key header는 필수입니다.");
        }
    }

    private Map<String, Object> normalize(Map<String, Object> request) {
        return request == null ? Map.of() : new LinkedHashMap<>(request);
    }

    private String requiredString(Map<String, Object> request, String field) {
        Object value = request.get(field);
        if (value == null || value.toString().isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + "는 필수입니다.");
        }
        return value.toString();
    }

    private long requiredLong(Map<String, Object> request, String field) {
        Object value = request.get(field);
        if (value instanceof Number number) {
            return number.longValue();
        }
        try {
            return Long.parseLong(requiredString(request, field));
        } catch (NumberFormatException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + "는 숫자여야 합니다.");
        }
    }

    private int requiredInt(Map<String, Object> request, String field) {
        Object value = request.get(field);
        if (value instanceof Number number) {
            return number.intValue();
        }
        try {
            return Integer.parseInt(requiredString(request, field));
        } catch (NumberFormatException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + "는 숫자여야 합니다.");
        }
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> requiredList(Map<String, Object> request, String field) {
        Object value = request.get(field);
        if (!(value instanceof List<?> list) || list.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + "는 비어 있을 수 없습니다.");
        }
        return (List<Map<String, Object>>) list;
    }

    private Number number(Object value) {
        if (value instanceof Number number) {
            return number;
        }
        return Integer.parseInt(value.toString());
    }

    private String hash(Object value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(writeJson(value).getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "요청 payload를 JSON으로 직렬화할 수 없습니다.");
        }
    }

    private Map<String, Object> readJson(String json) {
        try {
            return objectMapper.readValue(json, new TypeReference<>() {
            });
        } catch (JsonProcessingException ex) {
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "idempotency_replay_failed", "저장된 idempotency 응답을 읽을 수 없습니다.");
        }
    }

    private interface Command {
        Map<String, Object> execute();
    }
}
