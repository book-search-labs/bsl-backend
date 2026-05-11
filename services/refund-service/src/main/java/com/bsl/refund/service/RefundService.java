package com.bsl.refund.service;

import com.bsl.refund.client.DownstreamCallException;
import com.bsl.refund.client.RefundDownstreamClient;
import com.bsl.refund.common.ApiException;
import com.bsl.refund.common.ResponseSupport;
import com.bsl.refund.repository.IdempotencyRecord;
import com.bsl.refund.repository.RefundItem;
import com.bsl.refund.repository.RefundRecord;
import com.bsl.refund.repository.RefundStore;
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
import java.util.Optional;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RefundService {
    private static final String SERVICE_NAME = "refund-service";
    private static final String CREATE_REFUND = "CREATE_REFUND";
    private static final String APPROVE_REFUND = "APPROVE_REFUND";
    private static final String PROCESS_REFUND = "PROCESS_REFUND";
    private static final String PROCESSING = "PROCESSING";
    private static final String SUCCEEDED = "SUCCEEDED";
    private static final String FAILED = "FAILED";

    private final RefundStore store;
    private final RefundDownstreamClient downstreamClient;
    private final ObjectMapper objectMapper;

    public RefundService(RefundStore store, RefundDownstreamClient downstreamClient, ObjectMapper objectMapper) {
        this.store = store;
        this.downstreamClient = downstreamClient;
        this.objectMapper = objectMapper.copy().configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true);
    }

    @Transactional
    public Map<String, Object> create(Map<String, Object> request, String idempotencyKey, String traceId, String requestId) {
        return executeIdempotent(CREATE_REFUND, request, idempotencyKey, () -> createRefund(request, traceId, requestId));
    }

    @Transactional(readOnly = true)
    public Map<String, Object> get(String refundId, String traceId, String requestId) {
        RefundRecord refund = findRefund(refundId);
        return response(refund, store.findRefundItems(refundId), traceId, requestId);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> listByOrder(String orderId, String traceId, String requestId) {
        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.put("refunds", store.findRefundsByOrderId(orderId).stream().map(this::summary).toList());
        return response;
    }

    @Transactional(readOnly = true)
    public Map<String, Object> list(String orderId, String traceId, String requestId) {
        List<RefundRecord> refunds = orderId == null || orderId.isBlank()
            ? store.findAllRefunds()
            : store.findRefundsByOrderId(orderId);
        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.put("refunds", refunds.stream().map(this::summary).toList());
        return response;
    }

    @Transactional
    public Map<String, Object> approve(
        String refundId,
        Map<String, Object> request,
        String idempotencyKey,
        String traceId,
        String requestId
    ) {
        Map<String, Object> payload = normalize(request);
        payload.putIfAbsent("refund_id", refundId);
        return executeIdempotent(APPROVE_REFUND, payload, idempotencyKey, () -> approveRefund(refundId, traceId, requestId));
    }

    public Map<String, Object> process(
        String refundId,
        Map<String, Object> request,
        String idempotencyKey,
        String traceId,
        String requestId
    ) {
        Map<String, Object> payload = normalize(request);
        payload.putIfAbsent("refund_id", refundId);
        return executeIdempotent(PROCESS_REFUND, payload, idempotencyKey, () -> processRefund(refundId, traceId, requestId));
    }

    private Map<String, Object> createRefund(Map<String, Object> request, String traceId, String requestId) {
        Map<String, Object> payload = normalize(request);
        String refundId = optionalString(payload, "refund_id").orElse("refund-" + UUID.randomUUID());
        String orderId = requiredString(payload, "order_id");
        long checkoutId = requiredLong(payload, "checkout_id");
        String userId = optionalString(payload, "user_id").orElse(null);
        String paymentId = optionalString(payload, "payment_id").orElse(null);
        String inventoryReservationId = optionalString(payload, "inventory_reservation_id").orElse(null);
        String reason = requiredString(payload, "reason");
        BigDecimal totalAmount = requiredDecimal(payload, "amount");
        String currency = requiredString(payload, "currency");
        List<Map<String, Object>> items = optionalList(payload, "items");

        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.put("refund_id", refundId);
        response.put("order_id", orderId);
        response.put("checkout_id", checkoutId);
        response.put("status", "REQUESTED");
        response.put("amount", totalAmount);
        response.put("currency", currency);

        store.insertRefund(
            refundId,
            orderId,
            checkoutId,
            userId,
            paymentId,
            inventoryReservationId,
            "REQUESTED",
            reason,
            totalAmount,
            currency,
            writeJson(payload),
            writeJson(response)
        );
        for (Map<String, Object> item : items) {
            store.insertRefundItem(
                refundId,
                requiredString(item, "book_id"),
                requiredInt(item, "quantity"),
                optionalDecimal(item, "amount").orElse(BigDecimal.ZERO)
            );
        }
        recordEvent(refundId, "REFUND_REQUESTED", response);
        return response;
    }

    private Map<String, Object> approveRefund(String refundId, String traceId, String requestId) {
        RefundRecord refund = findRefund(refundId);
        if (!List.of("REQUESTED", "APPROVED").contains(refund.status())) {
            throw new ApiException(HttpStatus.CONFLICT, "refund_not_approvable", "현재 상태에서는 환불을 승인할 수 없습니다.");
        }
        Map<String, Object> response = response(refund, store.findRefundItems(refundId), traceId, requestId);
        response.put("status", "APPROVED");
        store.updateRefundStatus(refundId, "APPROVED", writeJson(response), null);
        recordEvent(refundId, "REFUND_APPROVED", response);
        return response;
    }

    private Map<String, Object> processRefund(String refundId, String traceId, String requestId) {
        RefundRecord refund = findRefund(refundId);
        if ("COMPLETED".equals(refund.status())) {
            return response(refund, store.findRefundItems(refundId), traceId, requestId);
        }
        if (!List.of("APPROVED", "FAILED_RETRYING", "UNKNOWN").contains(refund.status())) {
            throw new ApiException(HttpStatus.CONFLICT, "refund_not_processable", "승인되지 않은 환불은 처리할 수 없습니다.");
        }
        store.updateRefundStatus(refundId, "PROCESSING", null, null);
        recordEvent(refundId, "REFUND_PROCESSING", Map.of("refund_id", refundId, "status", "PROCESSING"));

        Optional<Map<String, Object>> paymentCancellation = cancelPayment(refund, traceId, requestId);
        if (paymentCancellation.isEmpty()) {
            return markUnknown(refund, "payment_cancel_unknown", "PG 취소 응답을 확인할 수 없습니다.", traceId, requestId);
        }

        Optional<Map<String, Object>> inventoryRelease = releaseInventory(refund, traceId, requestId);
        if (inventoryRelease.isEmpty()) {
            return markUnknown(refund, "inventory_release_unknown", "재고 보상 응답을 확인할 수 없습니다.", traceId, requestId);
        }

        Map<String, Object> response = response(refund, store.findRefundItems(refundId), traceId, requestId);
        response.put("status", "COMPLETED");
        response.put("payment_cancellation", paymentCancellation.get());
        inventoryRelease.ifPresent(value -> response.put("inventory_release", value));
        store.updateRefundStatus(refundId, "COMPLETED", writeJson(response), null);
        recordEvent(refundId, "REFUND_COMPLETED", response);
        return response;
    }

    private Optional<Map<String, Object>> cancelPayment(RefundRecord refund, String traceId, String requestId) {
        if (refund.paymentId() == null || refund.paymentId().isBlank()) {
            failRefund(refund.refundId(), "missing_payment_id", "환불 처리에는 payment_id가 필요합니다.");
        }
        String idempotencyKey = "refund:" + refund.refundId() + ":PAYMENT_CANCEL";
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("checkout_id", refund.checkoutId());
        request.put("payment_id", refund.paymentId());
        request.put("reason", "REFUND:" + refund.reason());
        try {
            return Optional.of(downstreamClient.cancelPayment(request, idempotencyKey, traceId, requestId));
        } catch (DownstreamCallException ex) {
            if (ex.isTimeout()) {
                return downstreamClient.findPaymentByIdempotencyKey(idempotencyKey, traceId, requestId);
            }
            failRefund(refund.refundId(), "payment_cancel_failed", ex.getMessage());
            return Optional.empty();
        }
    }

    private Optional<Map<String, Object>> releaseInventory(RefundRecord refund, String traceId, String requestId) {
        if (refund.inventoryReservationId() == null || refund.inventoryReservationId().isBlank()) {
            return Optional.of(Map.of("status", "SKIPPED", "reason", "inventory_reservation_id_missing"));
        }
        String idempotencyKey = "refund:" + refund.refundId() + ":INVENTORY_RELEASE";
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("checkout_id", refund.checkoutId());
        request.put("reservation_id", refund.inventoryReservationId());
        request.put("reason", "REFUND:" + refund.reason());
        try {
            return Optional.of(downstreamClient.releaseInventory(request, idempotencyKey, traceId, requestId));
        } catch (DownstreamCallException ex) {
            if (ex.isTimeout()) {
                return downstreamClient.findInventoryByIdempotencyKey(idempotencyKey, traceId, requestId);
            }
            failRefund(refund.refundId(), "inventory_release_failed", ex.getMessage());
            return Optional.empty();
        }
    }

    private Map<String, Object> markUnknown(
        RefundRecord refund,
        String errorCode,
        String message,
        String traceId,
        String requestId
    ) {
        Map<String, Object> response = response(refund, store.findRefundItems(refund.refundId()), traceId, requestId);
        response.put("status", "UNKNOWN");
        response.put("error_code", errorCode);
        response.put("error_message", message);
        store.updateRefundStatus(refund.refundId(), "UNKNOWN", writeJson(response), message);
        recordEvent(refund.refundId(), "REFUND_FAILED", response);
        return response;
    }

    private void failRefund(String refundId, String errorCode, String message) {
        Map<String, Object> payload = Map.of("refund_id", refundId, "status", "FAILED_RETRYING", "error_code", errorCode,
            "error_message", message);
        store.updateRefundStatus(refundId, "FAILED_RETRYING", writeJson(payload), message);
        recordEvent(refundId, "REFUND_FAILED", payload);
        throw new ApiException(HttpStatus.BAD_GATEWAY, errorCode, message);
    }

    private Map<String, Object> executeIdempotent(
        String operationType,
        Map<String, Object> request,
        String idempotencyKey,
        Command command
    ) {
        requireIdempotencyKey(idempotencyKey);
        Map<String, Object> payload = normalize(request);
        String requestHash = hash(payload);
        IdempotencyRecord existing = store.findIdempotency(idempotencyKey).orElse(null);
        if (existing != null) {
            validateIdempotency(existing, operationType, requestHash);
            if (SUCCEEDED.equals(existing.status())) {
                return readJson(existing.responsePayload());
            }
            if (PROCESSING.equals(existing.status())) {
                throw new ApiException(HttpStatus.CONFLICT, "idempotency_in_progress", "동일 Idempotency-Key 요청이 처리 중입니다.");
            }
            store.markIdempotencyProcessing(idempotencyKey);
        } else {
            try {
                store.insertIdempotency(idempotencyKey, operationType, requestHash, PROCESSING);
            } catch (DuplicateKeyException ex) {
                return executeIdempotent(operationType, request, idempotencyKey, command);
            }
        }

        try {
            Map<String, Object> response = command.execute();
            store.updateIdempotencySucceeded(idempotencyKey, writeJson(response));
            return response;
        } catch (ApiException ex) {
            store.updateIdempotencyFailed(idempotencyKey, ex.getMessage());
            throw ex;
        } catch (RuntimeException ex) {
            store.updateIdempotencyFailed(idempotencyKey, ex.getMessage());
            throw ex;
        }
    }

    private void validateIdempotency(IdempotencyRecord existing, String operationType, String requestHash) {
        if (!existing.operationType().equals(operationType)) {
            throw new ApiException(HttpStatus.CONFLICT, "idempotency_key_reused", "Idempotency-Key가 다른 operation에 재사용되었습니다.");
        }
        if (!existing.requestHash().equals(requestHash)) {
            throw new ApiException(HttpStatus.CONFLICT, "idempotency_payload_mismatch", "Idempotency-Key payload가 최초 요청과 다릅니다.");
        }
    }

    private RefundRecord findRefund(String refundId) {
        return store.findRefund(refundId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "refund_not_found", "환불을 찾을 수 없습니다."));
    }

    private Map<String, Object> response(RefundRecord refund, List<RefundItem> items, String traceId, String requestId) {
        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.putAll(summary(refund));
        response.put("items", items.stream().map(this::item).toList());
        return response;
    }

    private Map<String, Object> summary(RefundRecord refund) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("refund_id", refund.refundId());
        response.put("order_id", refund.orderId());
        response.put("checkout_id", refund.checkoutId());
        response.put("user_id", refund.userId());
        response.put("payment_id", refund.paymentId());
        response.put("inventory_reservation_id", refund.inventoryReservationId());
        response.put("status", refund.status());
        response.put("reason", refund.reason());
        response.put("amount", refund.totalAmount());
        response.put("currency", refund.currency());
        response.put("error_message", refund.errorMessage());
        return response;
    }

    private Map<String, Object> item(RefundItem item) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("book_id", item.bookId());
        response.put("quantity", item.quantity());
        response.put("amount", item.amount());
        return response;
    }

    private void recordEvent(String refundId, String eventType, Map<String, Object> payload) {
        Map<String, Object> eventPayload = new LinkedHashMap<>(payload);
        eventPayload.put("event_type", eventType);
        String json = writeJson(eventPayload);
        store.insertRefundEvent(refundId, eventType, json);
        store.insertOutboxEvent(refundId, eventType, "refund:" + refundId + ":" + eventType + ":" + UUID.randomUUID(), json);
    }

    private void requireIdempotencyKey(String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "missing_idempotency_key", "Idempotency-Key header는 필수입니다.");
        }
    }

    private Map<String, Object> normalize(Map<String, Object> request) {
        return request == null ? new LinkedHashMap<>() : new LinkedHashMap<>(request);
    }

    private Optional<String> optionalString(Map<String, Object> request, String field) {
        Object value = request.get(field);
        if (value == null || value.toString().isBlank()) {
            return Optional.empty();
        }
        return Optional.of(value.toString());
    }

    private String requiredString(Map<String, Object> request, String field) {
        return optionalString(request, field)
            .orElseThrow(() -> new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + "는 필수입니다."));
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
        return optionalDecimal(request, field)
            .orElseThrow(() -> new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + "는 필수입니다."));
    }

    private Optional<BigDecimal> optionalDecimal(Map<String, Object> request, String field) {
        if (!request.containsKey(field)) {
            return Optional.empty();
        }
        Object value = request.get(field);
        if (value instanceof BigDecimal decimal) {
            return Optional.of(decimal);
        }
        if (value instanceof Number number) {
            return Optional.of(BigDecimal.valueOf(number.doubleValue()));
        }
        return Optional.of(new BigDecimal(value.toString()));
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> optionalList(Map<String, Object> request, String field) {
        Object value = request.get(field);
        if (!(value instanceof List<?> list)) {
            return List.of();
        }
        return (List<Map<String, Object>>) list;
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
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "payload를 JSON으로 직렬화할 수 없습니다.");
        }
    }

    private Map<String, Object> readJson(String value) {
        try {
            return objectMapper.readValue(value, new TypeReference<>() {
            });
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(ex);
        }
    }

    @FunctionalInterface
    private interface Command {
        Map<String, Object> execute();
    }
}
