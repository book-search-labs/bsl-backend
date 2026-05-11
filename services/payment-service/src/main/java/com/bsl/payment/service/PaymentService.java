package com.bsl.payment.service;

import com.bsl.payment.common.ApiException;
import com.bsl.payment.common.ResponseSupport;
import com.bsl.payment.repository.IdempotencyRecord;
import com.bsl.payment.repository.PaymentStore;
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
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentService {
    private static final String SERVICE_NAME = "payment-service";
    private static final String AUTHORIZE_PAYMENT = "AUTHORIZE_PAYMENT";
    private static final String CANCEL_PAYMENT = "CANCEL_PAYMENT";
    private static final String PROCESSING = "PROCESSING";

    private final PaymentStore store;
    private final ObjectMapper objectMapper;
    private final FailureModeService failureModeService;

    @Autowired
    public PaymentService(PaymentStore store, ObjectMapper objectMapper, FailureModeService failureModeService) {
        this.store = store;
        this.objectMapper = objectMapper.copy().configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true);
        this.failureModeService = failureModeService;
    }

    PaymentService(PaymentStore store, ObjectMapper objectMapper) {
        this(store, objectMapper, new FailureModeService());
    }

    @Transactional
    public Map<String, Object> authorize(
        Map<String, Object> request,
        String idempotencyKey,
        String traceId,
        String requestId
    ) {
        return executeIdempotent(AUTHORIZE_PAYMENT, request, idempotencyKey, () -> createAuthorization(request, idempotencyKey, traceId, requestId));
    }

    @Transactional
    public Map<String, Object> cancel(
        Map<String, Object> request,
        String idempotencyKey,
        String traceId,
        String requestId
    ) {
        return executeIdempotent(CANCEL_PAYMENT, request, idempotencyKey, () -> createCancellation(request, idempotencyKey, traceId, requestId));
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

    private Map<String, Object> createAuthorization(
        Map<String, Object> request,
        String idempotencyKey,
        String traceId,
        String requestId
    ) {
        Map<String, Object> payload = normalize(request);
        long checkoutId = requiredLong(payload, "checkout_id");
        String orderId = requiredString(payload, "order_id");
        BigDecimal amount = requiredDecimal(payload, "amount");
        String currency = requiredString(payload, "currency");
        requiredString(payload, "method");
        String paymentId = "pay-" + UUID.randomUUID();
        String pgTransactionId = "pg-" + UUID.randomUUID();

        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.put("payment_id", paymentId);
        response.put("checkout_id", checkoutId);
        response.put("order_id", orderId);
        response.put("status", "AUTHORIZED");
        response.put("pg_transaction_id", pgTransactionId);
        response.put("amount", amount);
        response.put("currency", currency);

        store.insertAuthorization(paymentId, checkoutId, orderId, amount, currency, "AUTHORIZED", idempotencyKey, pgTransactionId, writeJson(response));
        return response;
    }

    private Map<String, Object> createCancellation(
        Map<String, Object> request,
        String idempotencyKey,
        String traceId,
        String requestId
    ) {
        Map<String, Object> payload = normalize(request);
        long checkoutId = requiredLong(payload, "checkout_id");
        String paymentId = requiredString(payload, "payment_id");
        requiredString(payload, "reason");
        String cancellationId = "pay-cancel-" + UUID.randomUUID();

        Map<String, Object> response = ResponseSupport.base(SERVICE_NAME, traceId, requestId);
        response.put("cancellation_id", cancellationId);
        response.put("payment_id", paymentId);
        response.put("checkout_id", checkoutId);
        response.put("status", "CANCELLED");

        store.insertCancellation(cancellationId, paymentId, checkoutId, "CANCELLED", idempotencyKey, writeJson(response));
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

    private BigDecimal requiredDecimal(Map<String, Object> request, String field) {
        if (!request.containsKey(field)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + "는 필수입니다.");
        }
        Object value = request.get(field);
        if (value instanceof BigDecimal decimal) {
            return decimal;
        }
        if (value instanceof Number number) {
            return BigDecimal.valueOf(number.doubleValue());
        }
        return new BigDecimal(value.toString());
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
