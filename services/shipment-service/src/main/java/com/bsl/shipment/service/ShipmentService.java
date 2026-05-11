package com.bsl.shipment.service;

import com.bsl.shipment.common.ApiException;
import com.bsl.shipment.common.ResponseSupport;
import com.bsl.shipment.repository.IdempotencyRecord;
import com.bsl.shipment.repository.ShipmentStore;
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
public class ShipmentService {
    private static final String SERVICE_NAME = "shipment-service";
    private static final String CREATE_SHIPMENT = "CREATE_SHIPMENT";
    private static final String CANCEL_SHIPMENT = "CANCEL_SHIPMENT";
    private static final String PROCESSING = "PROCESSING";

    private final ShipmentStore store;
    private final ObjectMapper objectMapper;
    private final FailureModeService failureModeService;

    @Autowired
    public ShipmentService(ShipmentStore store, ObjectMapper objectMapper, FailureModeService failureModeService) {
        this.store = store;
        this.objectMapper = objectMapper.copy().configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true);
        this.failureModeService = failureModeService;
    }

    ShipmentService(ShipmentStore store, ObjectMapper objectMapper) {
        this(store, objectMapper, new FailureModeService());
    }

    @Transactional
    public Map<String, Object> create(Map<String, Object> request, String idempotencyKey, String traceId, String requestId) {
        return executeIdempotent(CREATE_SHIPMENT, request, idempotencyKey, () -> createShipment(request, idempotencyKey, traceId, requestId));
    }

    @Transactional
    public Map<String, Object> cancel(Map<String, Object> request, String idempotencyKey, String traceId, String requestId) {
        return executeIdempotent(CANCEL_SHIPMENT, request, idempotencyKey, () -> cancelShipment(request, traceId, requestId));
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

    private Map<String, Object> createShipment(Map<String, Object> request, String idempotencyKey, String traceId, String requestId) {
        Map<String, Object> payload = normalize(request);
        long checkoutId = requiredLong(payload, "checkout_id");
        String orderId = requiredString(payload, "order_id");
        Object shippingAddress = requiredObject(payload, "shipping_address");
        requiredList(payload, "items");
        String shipmentId = "ship-" + UUID.randomUUID();

        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.put("shipment_id", shipmentId);
        response.put("checkout_id", checkoutId);
        response.put("order_id", orderId);
        response.put("status", "REQUESTED");

        store.insertShipment(shipmentId, checkoutId, orderId, "REQUESTED", idempotencyKey, writeJson(shippingAddress), writeJson(response));
        return response;
    }

    private Map<String, Object> cancelShipment(Map<String, Object> request, String traceId, String requestId) {
        Map<String, Object> payload = normalize(request);
        long checkoutId = requiredLong(payload, "checkout_id");
        String shipmentId = requiredString(payload, "shipment_id");
        requiredString(payload, "reason");
        Map<String, Object> shipment = store.findShipment(shipmentId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "shipment_not_found", "배송 요청을 찾을 수 없습니다."));
        store.markShipmentCancelled(shipmentId);

        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.put("shipment_id", shipmentId);
        response.put("checkout_id", checkoutId);
        response.put("order_id", shipment.get("order_id"));
        response.put("status", "CANCELLED");
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

    private Object requiredObject(Map<String, Object> request, String field) {
        Object value = request.get(field);
        if (value == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + "는 필수입니다.");
        }
        return value;
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

    private void requiredList(Map<String, Object> request, String field) {
        Object value = request.get(field);
        if (!(value instanceof List<?> list) || list.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + "는 비어 있을 수 없습니다.");
        }
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
