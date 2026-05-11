package com.bsl.order.service;

import com.bsl.order.common.ApiException;
import com.bsl.order.common.ResponseSupport;
import com.bsl.order.repository.IdempotencyRecord;
import com.bsl.order.repository.OrderStore;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private static final String SERVICE_NAME = "order-service";
    private static final String CREATE_ORDER = "CREATE_ORDER";
    private static final String PROCESSING = "PROCESSING";
    private static final String SUCCEEDED = "SUCCEEDED";

    private final OrderStore store;
    private final ObjectMapper objectMapper;

    public OrderService(OrderStore store, ObjectMapper objectMapper) {
        this.store = store;
        this.objectMapper = objectMapper.copy().configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true);
    }

    @Transactional
    public Map<String, Object> createOrder(
        Map<String, Object> request,
        String idempotencyKey,
        String traceId,
        String requestId
    ) {
        requireIdempotencyKey(idempotencyKey);
        Map<String, Object> payload = normalize(request);
        String requestHash = hash(payload);
        IdempotencyRecord existing = store.findIdempotency(idempotencyKey).orElse(null);
        if (existing != null) {
            return replay(existing, CREATE_ORDER, requestHash);
        }
        try {
            store.insertIdempotency(idempotencyKey, CREATE_ORDER, requestHash, PROCESSING);
        } catch (DuplicateKeyException ex) {
            return replay(store.findIdempotency(idempotencyKey).orElseThrow(() -> ex), CREATE_ORDER, requestHash);
        }

        Map<String, Object> response = createNewOrder(payload, traceId, requestId);
        store.updateIdempotencySucceeded(idempotencyKey, writeJson(response));
        return response;
    }

    @Transactional(readOnly = true)
    public Map<String, Object> getOrder(String orderId, String traceId, String requestId) {
        Map<String, Object> order = store.findOrder(orderId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "order_not_found", "주문을 찾을 수 없습니다."));
        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.putAll(order);
        response.put("lines", store.findOrderLines(orderId));
        return response;
    }

    private Map<String, Object> createNewOrder(Map<String, Object> request, String traceId, String requestId) {
        long checkoutId = requiredLong(request, "checkout_id");
        String userId = requiredString(request, "user_id");
        BigDecimal totalAmount = requiredDecimal(request, "total_amount");
        String currency = requiredString(request, "currency");
        List<Map<String, Object>> items = requiredList(request, "items");
        String orderId = "ord-" + UUID.randomUUID();

        store.insertOrder(orderId, userId, checkoutId, "PENDING", totalAmount, currency);
        for (Map<String, Object> item : items) {
            store.insertOrderLine(
                orderId,
                requiredString(item, "book_id"),
                stringValue(item.get("title")),
                requiredInt(item, "quantity"),
                decimal(item.getOrDefault("unit_price", BigDecimal.ZERO))
            );
        }

        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.put("order_id", orderId);
        response.put("checkout_id", checkoutId);
        response.put("user_id", userId);
        response.put("status", "PENDING");
        response.put("total_amount", totalAmount);
        response.put("currency", currency);
        response.put("lines", items);
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
        if (request == null) {
            return Map.of();
        }
        return new LinkedHashMap<>(request);
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

    private BigDecimal requiredDecimal(Map<String, Object> request, String field) {
        if (!request.containsKey(field)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + "는 필수입니다.");
        }
        return decimal(request.get(field));
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> requiredList(Map<String, Object> request, String field) {
        Object value = request.get(field);
        if (!(value instanceof List<?> list) || list.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + "는 비어 있을 수 없습니다.");
        }
        return (List<Map<String, Object>>) list;
    }

    private BigDecimal decimal(Object value) {
        if (value instanceof BigDecimal decimal) {
            return decimal;
        }
        if (value instanceof Number number) {
            return BigDecimal.valueOf(number.doubleValue());
        }
        return new BigDecimal(value.toString());
    }

    private String stringValue(Object value) {
        return value == null ? null : value.toString();
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
}

