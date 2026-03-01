package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.common.JsonUtils;
import com.bsl.commerce.config.PaymentProperties;
import com.bsl.commerce.repository.OrderRepository;
import com.bsl.commerce.repository.PaymentRepository;
import com.bsl.commerce.service.payment.PaymentGateway;
import com.bsl.commerce.service.payment.PaymentGatewayFactory;
import com.bsl.commerce.service.payment.PaymentProvider;
import com.bsl.commerce.service.payment.PaymentStatus;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Metrics;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDate;
import java.time.Instant;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentService {
    private static final Logger logger = LoggerFactory.getLogger(PaymentService.class);

    private final PaymentRepository paymentRepository;
    private final OrderRepository orderRepository;
    private final OrderService orderService;
    private final InventoryService inventoryService;
    private final ShipmentService shipmentService;
    private final LoyaltyPointService loyaltyPointService;
    private final LedgerService ledgerService;
    private final PaymentGatewayFactory paymentGatewayFactory;
    private final PaymentProperties paymentProperties;
    private final ObjectMapper objectMapper;

    public PaymentService(
        PaymentRepository paymentRepository,
        OrderRepository orderRepository,
        OrderService orderService,
        InventoryService inventoryService,
        ShipmentService shipmentService,
        LoyaltyPointService loyaltyPointService,
        LedgerService ledgerService,
        PaymentGatewayFactory paymentGatewayFactory,
        PaymentProperties paymentProperties,
        ObjectMapper objectMapper
    ) {
        this.paymentRepository = paymentRepository;
        this.orderRepository = orderRepository;
        this.orderService = orderService;
        this.inventoryService = inventoryService;
        this.shipmentService = shipmentService;
        this.loyaltyPointService = loyaltyPointService;
        this.ledgerService = ledgerService;
        this.paymentGatewayFactory = paymentGatewayFactory;
        this.paymentProperties = paymentProperties;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Map<String, Object> createPayment(long orderId, int amount, String method, String idempotencyKey) {
        return createPayment(orderId, amount, method, idempotencyKey, null, null, null);
    }

    @Transactional
    public Map<String, Object> createPayment(
        long orderId,
        int amount,
        String method,
        String idempotencyKey,
        String providerHint,
        String returnUrl,
        String webhookUrl
    ) {
        if (idempotencyKey != null) {
            Map<String, Object> existing = paymentRepository.findPaymentByIdempotencyKey(idempotencyKey);
            if (existing != null) {
                return existing;
            }
        }

        Map<String, Object> order = orderRepository.findOrderById(orderId);
        if (order == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "주문 정보를 찾을 수 없습니다.");
        }
        String orderStatus = JdbcUtils.asString(order.get("status"));
        if (!"PAYMENT_PENDING".equals(orderStatus) && !"CREATED".equals(orderStatus)) {
            throw new ApiException(HttpStatus.CONFLICT, "invalid_state", "현재 상태에서는 결제를 진행할 수 없습니다.");
        }
        int totalAmount = JdbcUtils.asInt(order.get("total_amount")) == null ? 0 : JdbcUtils.asInt(order.get("total_amount"));
        if (amount != totalAmount) {
            throw new ApiException(HttpStatus.CONFLICT, "amount_mismatch", "결제 금액이 주문 금액과 일치하지 않습니다.");
        }

        String currency = JdbcUtils.asString(order.get("currency"));
        if (currency == null) {
            currency = "KRW";
        }

        PaymentProvider provider = resolveRequestedProvider(providerHint);
        PaymentGateway gateway = paymentGatewayFactory.get(provider);

        long paymentId;
        try {
            paymentId = paymentRepository.insertPayment(
                orderId,
                method == null ? "CARD" : method,
                gateway.initiatedStatus(),
                amount,
                currency,
                gateway.provider().name(),
                null,
                idempotencyKey
            );
        } catch (DuplicateKeyException ex) {
            if (idempotencyKey != null) {
                Map<String, Object> existing = paymentRepository.findPaymentByIdempotencyKey(idempotencyKey);
                if (existing != null) {
                    return existing;
                }
            }
            throw ex;
        }

        String resolvedReturnUrl = firstNonBlank(trimToNull(returnUrl), trimToNull(paymentProperties.getDefaultReturnUrl()));
        String resolvedWebhookUrl = firstNonBlank(
            trimToNull(webhookUrl),
            buildDefaultWebhookUrl(provider)
        );
        String checkoutBaseUrl = firstNonBlank(
            trimToNull(paymentProperties.getMockCheckoutBaseUrl()),
            "http://localhost:8090/checkout"
        );

        PaymentGateway.CheckoutSession session = gateway.createCheckoutSession(
            new PaymentGateway.CreateCheckoutSessionRequest(
                paymentId,
                orderId,
                amount,
                currency,
                resolvedReturnUrl,
                resolvedWebhookUrl,
                checkoutBaseUrl,
                paymentProperties.getSessionTtlSeconds()
            )
        );

        paymentRepository.updateCheckoutContext(
            paymentId,
            session.sessionId(),
            resolvedReturnUrl,
            resolvedWebhookUrl,
            session.checkoutUrl(),
            session.expiresAt()
        );

        Map<String, Object> initiatedPayload = new LinkedHashMap<>();
        initiatedPayload.put("checkout_session_id", session.sessionId());
        initiatedPayload.put("checkout_url", session.checkoutUrl());
        initiatedPayload.put("expires_at", session.expiresAt() == null ? null : session.expiresAt().toString());
        initiatedPayload.put("return_url", resolvedReturnUrl);
        initiatedPayload.put("webhook_url", resolvedWebhookUrl);
        paymentRepository.insertPaymentEvent(
            paymentId,
            gateway.initiatedEventType(),
            null,
            JsonUtils.toJson(objectMapper, initiatedPayload)
        );

        return paymentRepository.findPayment(paymentId);
    }

    @Transactional
    public Map<String, Object> mockComplete(long paymentId, String result) {
        Map<String, Object> payment = paymentRepository.findPayment(paymentId);
        if (payment == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "결제 정보를 찾을 수 없습니다.");
        }
        String status = JdbcUtils.asString(payment.get("status"));
        if ("CAPTURED".equals(status) || "FAILED".equals(status) || "CANCELED".equals(status)) {
            return payment;
        }

        PaymentGateway gateway = resolveGatewayForPayment(payment);
        if (!gateway.supportsMockComplete()) {
            throw new ApiException(
                HttpStatus.CONFLICT,
                "mock_complete_not_supported",
                "선택한 결제 제공자에서 mock/complete를 지원하지 않습니다."
            );
        }

        PaymentGateway.MockCompletionDecision completion = gateway.completeMock(paymentId, result);

        Map<String, Object> payload = new LinkedHashMap<>();
        String eventId = "mock_" + paymentId + "_" + UUID.randomUUID().toString().replace("-", "");
        payload.put("event_id", eventId);
        payload.put("payment_id", paymentId);
        payload.put("status", completion.getStatus());
        payload.put("provider", gateway.provider().name());
        payload.put("occurred_at", Instant.now().toString());
        payload.put("source", "mock_complete");
        if (completion.getProviderPaymentId() != null) {
            payload.put("provider_payment_id", completion.getProviderPaymentId());
        }
        if (completion.getFailureReason() != null) {
            payload.put("failure_reason", completion.getFailureReason());
        }

        processWebhookInternal(gateway.provider(), payload, eventId, true, JsonUtils.toJson(objectMapper, payload), null);

        return paymentRepository.findPayment(paymentId);
    }

    @Transactional
    public Map<String, Object> handleWebhook(
        String provider,
        String rawPayload,
        String signature,
        String providerEventId
    ) {
        PaymentProvider paymentProvider = resolveProviderFromPath(provider);
        Map<String, Object> payload = parseWebhookPayload(rawPayload);
        String rawForSignature = rawPayload == null ? JsonUtils.toJson(objectMapper, payload) : rawPayload;
        return processWebhookInternal(paymentProvider, payload, providerEventId, false, rawForSignature, signature);
    }

    @Transactional
    public void handleWebhook(String provider, Map<String, Object> payload, String providerEventId) {
        PaymentProvider paymentProvider = resolveProviderFromPath(provider);
        processWebhookInternal(
            paymentProvider,
            payload == null ? Map.of() : payload,
            providerEventId,
            true,
            JsonUtils.toJson(objectMapper, payload),
            null
        );
    }

    public Map<String, Object> getPayment(long paymentId) {
        Map<String, Object> payment = paymentRepository.findPayment(paymentId);
        if (payment == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "결제 정보를 찾을 수 없습니다.");
        }
        return payment;
    }

    @Transactional
    public Map<String, Object> cancelPayment(long paymentId, String reason) {
        Map<String, Object> payment = paymentRepository.findPayment(paymentId);
        if (payment == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "결제 정보를 찾을 수 없습니다.");
        }
        String status = JdbcUtils.asString(payment.get("status"));
        if ("CANCELED".equals(status)) {
            return payment;
        }
        paymentRepository.updatePaymentStatus(paymentId, "CANCELED", JdbcUtils.asString(payment.get("provider_payment_id")), reason);
        paymentRepository.insertPaymentEvent(paymentId, "PAYMENT_CANCELED", null, null);
        return paymentRepository.findPayment(paymentId);
    }

    public List<Map<String, Object>> listPayments(
        int limit,
        String status,
        String provider,
        String fromDate,
        String toDate
    ) {
        int resolved = Math.min(Math.max(limit, 1), 200);
        LocalDate from = parseLocalDateOrNull(fromDate, "from");
        LocalDate to = parseLocalDateOrNull(toDate, "to");
        if (from != null && to != null && to.isBefore(from)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "to 날짜는 from 날짜보다 빠를 수 없습니다.");
        }
        return paymentRepository.listPayments(
            resolved,
            trimToNull(status),
            trimToNull(provider),
            from,
            to
        );
    }

    public List<Map<String, Object>> listWebhookEvents(long paymentId, int limit) {
        int resolved = Math.min(Math.max(limit, 1), 200);
        return paymentRepository.listWebhookEventsByPaymentId(paymentId, resolved);
    }

    public List<Map<String, Object>> listWebhookEventsForOps(int limit, String processStatus, String provider) {
        int resolved = Math.min(Math.max(limit, 1), 200);
        return paymentRepository.listWebhookEvents(
            resolved,
            trimToNull(processStatus),
            trimToNull(provider)
        );
    }

    @Transactional
    public Map<String, Object> retryWebhookEvent(String eventId) {
        return retryWebhookEvent(eventId, true);
    }

    @Transactional
    Map<String, Object> retryWebhookEventForScheduler(String eventId) {
        return retryWebhookEvent(eventId, false);
    }

    private Map<String, Object> retryWebhookEvent(String eventId, boolean trackRetryLifecycle) {
        Map<String, Object> event = paymentRepository.findWebhookEventByEventId(eventId);
        if (event == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "웹훅 이벤트를 찾을 수 없습니다.");
        }
        String providerRaw = JdbcUtils.asString(event.get("provider"));
        PaymentProvider provider = resolveProviderFromPath(providerRaw);

        String payloadJson = JdbcUtils.asString(event.get("payload_json"));
        Map<String, Object> payload = parseWebhookPayload(payloadJson == null ? "{}" : payloadJson);
        String retryEventId = eventId + ":retry:" + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        if (trackRetryLifecycle) {
            paymentRepository.markWebhookRetryAttempt(eventId, 0, "manual_retry_attempt");
            Metrics.counter("commerce.webhook.retry.events.total", "outcome", "manual_attempt").increment();
        }

        try {
            Map<String, Object> result = processWebhookInternal(provider, payload, retryEventId, true, payloadJson, null);
            if (trackRetryLifecycle) {
                String retryStatus = JdbcUtils.asString(result.get("status"));
                if ("processed".equals(retryStatus) || "ignored".equals(retryStatus) || "duplicate".equals(retryStatus)) {
                    paymentRepository.markWebhookRetryResolved(eventId, "RETRIED", "manual_retry_" + retryStatus);
                }
                Metrics.counter(
                    "commerce.webhook.retry.events.total",
                    "outcome",
                    retryStatus == null ? "manual_unknown" : "manual_" + retryStatus
                ).increment();
            }
            return result;
        } catch (ApiException ex) {
            if (trackRetryLifecycle) {
                Metrics.counter("commerce.webhook.retry.events.total", "outcome", "manual_failed_api").increment();
            }
            throw ex;
        } catch (Exception ex) {
            if (trackRetryLifecycle) {
                Metrics.counter("commerce.webhook.retry.events.total", "outcome", "manual_failed_internal").increment();
            }
            throw ex;
        }
    }

    private Map<String, Object> processWebhookInternal(
        PaymentProvider provider,
        Map<String, Object> payload,
        String providerEventId,
        boolean skipSignatureVerification,
        String rawPayload,
        String signature
    ) {
        String payloadJson = JsonUtils.toJson(objectMapper, payload);
        String eventId = resolveWebhookEventId(providerEventId, payload, payloadJson, provider);
        Long paymentId = extractPaymentId(payload);

        PaymentRepository.WebhookInsertResult insertResult = paymentRepository.insertWebhookEvent(
            provider.name(),
            eventId,
            paymentId,
            false,
            payloadJson,
            "RECEIVED"
        );
        incrementWebhookMetric(provider, "received");
        if (insertResult == PaymentRepository.WebhookInsertResult.DUPLICATE) {
            incrementWebhookMetric(provider, "duplicate");
            logger.info("payment_webhook_duplicate provider={} event_id={} payment_id={}", provider.name(), eventId, paymentId);
            return webhookResult("duplicate", eventId, paymentId, null);
        }

        if (!skipSignatureVerification) {
            boolean signatureOk = verifyWebhookSignature(provider, rawPayload, signature);
            if (!signatureOk) {
                paymentRepository.updateWebhookEventStatus(eventId, false, "FAILED", "invalid_signature");
                incrementWebhookMetric(provider, "failed_invalid_signature");
                logger.warn("payment_webhook_invalid_signature provider={} event_id={} payment_id={}", provider.name(), eventId, paymentId);
                throw new ApiException(HttpStatus.UNAUTHORIZED, "invalid_signature", "웹훅 서명 검증에 실패했습니다.");
            }
        }

        if (paymentId == null) {
            paymentRepository.updateWebhookEventStatus(eventId, true, "IGNORED", "missing_payment_id");
            incrementWebhookMetric(provider, "ignored_missing_payment_id");
            logger.warn("payment_webhook_ignored_missing_payment_id provider={} event_id={}", provider.name(), eventId);
            return webhookResult("ignored", eventId, null, "missing_payment_id");
        }

        Map<String, Object> payment = paymentRepository.findPayment(paymentId);
        if (payment == null) {
            paymentRepository.updateWebhookEventStatus(eventId, true, "IGNORED", "payment_not_found");
            incrementWebhookMetric(provider, "ignored_payment_not_found");
            logger.warn("payment_webhook_ignored_payment_not_found provider={} event_id={} payment_id={}", provider.name(), eventId, paymentId);
            return webhookResult("ignored", eventId, paymentId, "payment_not_found");
        }

        PaymentStatus targetStatus = resolveWebhookTargetStatus(payload);
        if (targetStatus == null) {
            paymentRepository.updateWebhookEventStatus(eventId, true, "IGNORED", "unsupported_status");
            incrementWebhookMetric(provider, "ignored_unsupported_status");
            logger.info("payment_webhook_ignored_unsupported_status provider={} event_id={} payment_id={}", provider.name(), eventId, paymentId);
            return webhookResult("ignored", eventId, paymentId, "unsupported_status");
        }

        String currentStatusRaw = JdbcUtils.asString(payment.get("status"));
        PaymentStatus currentStatus;
        try {
            currentStatus = PaymentStatus.from(currentStatusRaw);
        } catch (IllegalArgumentException ex) {
            paymentRepository.updateWebhookEventStatus(eventId, true, "FAILED", "invalid_current_status");
            incrementWebhookMetric(provider, "failed_invalid_current_status");
            throw new ApiException(HttpStatus.CONFLICT, "invalid_state", "결제 상태가 올바르지 않습니다.");
        }

        if (!currentStatus.canTransitionTo(targetStatus)) {
            paymentRepository.updateWebhookEventStatus(eventId, true, "IGNORED", "invalid_transition");
            incrementWebhookMetric(provider, "ignored_invalid_transition");
            logger.info(
                "payment_webhook_ignored_invalid_transition provider={} event_id={} payment_id={} current_status={} target_status={}",
                provider.name(),
                eventId,
                paymentId,
                currentStatus.name(),
                targetStatus.name()
            );
            return webhookResult("ignored", eventId, paymentId, "invalid_transition");
        }

        if (currentStatus != targetStatus) {
            String providerPaymentId = resolveProviderPaymentId(payload, payment, targetStatus);
            String failureReason = targetStatus == PaymentStatus.FAILED ? resolveFailureReason(payload) : null;
            paymentRepository.updatePaymentStatus(paymentId, targetStatus.name(), providerPaymentId, failureReason);
            paymentRepository.insertPaymentEvent(
                paymentId,
                eventTypeForStatus(targetStatus),
                eventId,
                payloadJson
            );

            if (targetStatus == PaymentStatus.CAPTURED) {
                applyPostCaptureEffects(
                    paymentId,
                    JdbcUtils.asLong(payment.get("order_id")),
                    JdbcUtils.asString(payment.get("currency"))
                );
            }
        }

        paymentRepository.updateWebhookEventStatus(eventId, true, "PROCESSED", null);
        incrementWebhookMetric(provider, "processed");
        logger.info(
            "payment_webhook_processed provider={} event_id={} payment_id={} current_status={} target_status={}",
            provider.name(),
            eventId,
            paymentId,
            currentStatus.name(),
            targetStatus.name()
        );
        return webhookResult("processed", eventId, paymentId, null);
    }

    private void applyPostCaptureEffects(long paymentId, long orderId, String currency) {
        orderService.markPaid(orderId, String.valueOf(paymentId));

        List<Map<String, Object>> items = orderRepository.findOrderItems(orderId);
        for (Map<String, Object> item : items) {
            long skuId = JdbcUtils.asLong(item.get("sku_id"));
            long sellerId = JdbcUtils.asLong(item.get("seller_id"));
            int qty = JdbcUtils.asInt(item.get("qty"));
            long orderItemId = JdbcUtils.asLong(item.get("order_item_id"));
            String deductKey = "payment_" + paymentId + "_deduct_" + orderItemId;
            inventoryService.deduct(skuId, sellerId, qty, deductKey, "ORDER", String.valueOf(orderId));
        }
        ledgerService.recordPaymentCaptured(paymentId, orderId, items, currency);

        try {
            shipmentService.ensureShipmentForOrder(orderId);
        } catch (ApiException ex) {
            logger.warn(
                "shipment_auto_create_failed payment_id={} order_id={} code={}",
                paymentId,
                orderId,
                ex.getCode()
            );
        }

        Map<String, Object> order = orderRepository.findOrderById(orderId);
        if (order != null) {
            long userId = JdbcUtils.asLong(order.get("user_id"));
            int totalAmount = JdbcUtils.asInt(order.get("total_amount")) == null
                ? 0
                : JdbcUtils.asInt(order.get("total_amount"));
            loyaltyPointService.earnForOrder(userId, orderId, totalAmount, "ORDER_PAYMENT_COMPLETED");
        }
    }

    private PaymentGateway resolveGatewayForPayment(Map<String, Object> payment) {
        String providerValue = JdbcUtils.asString(payment.get("provider"));
        PaymentProvider provider;
        try {
            provider = providerValue == null ? resolveDefaultProvider() : PaymentProvider.from(providerValue);
        } catch (IllegalArgumentException ex) {
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "payment_provider_invalid", "결제 제공자 값이 올바르지 않습니다.");
        }
        return paymentGatewayFactory.get(provider);
    }

    private PaymentProvider resolveRequestedProvider(String providerHint) {
        if (providerHint == null || providerHint.isBlank()) {
            return resolveDefaultProvider();
        }
        try {
            return PaymentProvider.from(providerHint);
        } catch (IllegalArgumentException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "지원하지 않는 provider 입니다.");
        }
    }

    private PaymentProvider resolveDefaultProvider() {
        PaymentProvider configured = paymentProperties.getDefaultProvider();
        return configured == null ? PaymentProvider.MOCK : configured;
    }

    private PaymentProvider resolveProviderFromPath(String provider) {
        try {
            return PaymentProvider.from(provider);
        } catch (IllegalArgumentException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "지원하지 않는 provider 입니다.");
        }
    }

    private String buildDefaultWebhookUrl(PaymentProvider provider) {
        String configured = trimToNull(paymentProperties.getDefaultWebhookUrl());
        if (configured == null) {
            return "http://localhost:8091/api/v1/payments/webhook/" + provider.name().toLowerCase(Locale.ROOT);
        }
        if (configured.contains("{provider}")) {
            return configured.replace("{provider}", provider.name().toLowerCase(Locale.ROOT));
        }
        return configured;
    }

    private Map<String, Object> parseWebhookPayload(String rawPayload) {
        if (rawPayload == null || rawPayload.isBlank()) {
            return Map.of();
        }
        try {
            return objectMapper.readValue(rawPayload, new TypeReference<>() {
            });
        } catch (Exception ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "웹훅 payload 형식이 올바르지 않습니다.");
        }
    }

    private String resolveWebhookEventId(
        String providerEventId,
        Map<String, Object> payload,
        String payloadJson,
        PaymentProvider provider
    ) {
        String candidate = firstNonBlank(
            trimToNull(providerEventId),
            trimToNull(JdbcUtils.asString(payload.get("event_id"))),
            trimToNull(JdbcUtils.asString(payload.get("eventId")))
        );
        if (candidate != null) {
            return candidate;
        }
        return provider.name().toLowerCase(Locale.ROOT) + ":" + sha256Hex(payloadJson == null ? "" : payloadJson);
    }

    private Long extractPaymentId(Map<String, Object> payload) {
        if (payload == null) {
            return null;
        }
        Object value = payload.getOrDefault("payment_id", payload.get("paymentId"));
        return JdbcUtils.asLong(value);
    }

    private PaymentStatus resolveWebhookTargetStatus(Map<String, Object> payload) {
        String status = firstNonBlank(
            trimToNull(JdbcUtils.asString(payload.get("status"))),
            trimToNull(JdbcUtils.asString(payload.get("result"))),
            trimToNull(JdbcUtils.asString(payload.get("event_type"))),
            trimToNull(JdbcUtils.asString(payload.get("eventType")))
        );
        if (status == null) {
            return null;
        }
        String normalized = status.toUpperCase(Locale.ROOT);
        if (
            normalized.contains("CAPTURE")
                || normalized.contains("SUCCESS")
                || normalized.contains("PAID")
                || normalized.contains("APPROVED")
        ) {
            return PaymentStatus.CAPTURED;
        }
        if (normalized.contains("FAIL") || normalized.contains("ERROR")) {
            return PaymentStatus.FAILED;
        }
        if (normalized.contains("CANCEL")) {
            return PaymentStatus.CANCELED;
        }
        return null;
    }

    private String eventTypeForStatus(PaymentStatus status) {
        return switch (status) {
            case CAPTURED -> "CAPTURE_SUCCEEDED";
            case FAILED -> "CAPTURE_FAILED";
            case CANCELED -> "PAYMENT_CANCELED";
            case REFUNDED -> "PAYMENT_REFUNDED";
            case AUTHORIZED -> "PAYMENT_AUTHORIZED";
            case READY, PROCESSING, INITIATED -> "PAYMENT_UPDATED";
        };
    }

    private String resolveProviderPaymentId(Map<String, Object> payload, Map<String, Object> payment, PaymentStatus targetStatus) {
        String fromPayload = firstNonBlank(
            trimToNull(JdbcUtils.asString(payload.get("provider_payment_id"))),
            trimToNull(JdbcUtils.asString(payload.get("providerPaymentId"))),
            trimToNull(JdbcUtils.asString(payload.get("session_id"))),
            trimToNull(JdbcUtils.asString(payload.get("sessionId")))
        );
        if (fromPayload != null) {
            return fromPayload;
        }
        if (targetStatus == PaymentStatus.CAPTURED) {
            String checkoutSessionId = trimToNull(JdbcUtils.asString(payment.get("checkout_session_id")));
            if (checkoutSessionId != null) {
                return checkoutSessionId;
            }
        }
        return trimToNull(JdbcUtils.asString(payment.get("provider_payment_id")));
    }

    private String resolveFailureReason(Map<String, Object> payload) {
        return firstNonBlank(
            trimToNull(JdbcUtils.asString(payload.get("failure_reason"))),
            trimToNull(JdbcUtils.asString(payload.get("reason"))),
            trimToNull(JdbcUtils.asString(payload.get("error"))),
            "provider_failed"
        );
    }

    private boolean verifyWebhookSignature(PaymentProvider provider, String rawPayload, String signatureHeader) {
        String secret = resolveWebhookSecret(provider);
        if (secret == null || secret.isBlank()) {
            return true;
        }
        String provided = normalizeSignature(signatureHeader);
        if (provided == null) {
            return false;
        }
        String expected = hmacSha256Hex(secret, rawPayload == null ? "" : rawPayload);
        return MessageDigest.isEqual(
            expected.getBytes(StandardCharsets.UTF_8),
            provided.getBytes(StandardCharsets.UTF_8)
        );
    }

    private String resolveWebhookSecret(PaymentProvider provider) {
        return switch (provider) {
            case MOCK -> trimToNull(paymentProperties.getMockWebhookSecret());
            case LOCAL_SIM -> trimToNull(paymentProperties.getLocalSimWebhookSecret());
            case TOSS, STRIPE -> trimToNull(paymentProperties.getMockWebhookSecret());
        };
    }

    private String normalizeSignature(String signatureHeader) {
        String signature = trimToNull(signatureHeader);
        if (signature == null) {
            return null;
        }
        String normalized = signature.toLowerCase(Locale.ROOT);
        if (normalized.startsWith("sha256=")) {
            normalized = normalized.substring("sha256=".length());
        }
        return normalized;
    }

    private String hmacSha256Hex(String secret, String body) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            byte[] hash = mac.doFinal(body.getBytes(StandardCharsets.UTF_8));
            return java.util.HexFormat.of().formatHex(hash);
        } catch (Exception ex) {
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "internal_error", "웹훅 서명 검증 처리 중 오류가 발생했습니다.");
        }
    }

    private String sha256Hex(String body) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(body.getBytes(StandardCharsets.UTF_8));
            return java.util.HexFormat.of().formatHex(bytes);
        } catch (Exception ex) {
            return UUID.randomUUID().toString().replace("-", "");
        }
    }

    private Map<String, Object> webhookResult(String status, String eventId, Long paymentId, String reason) {
        Map<String, Object> result = new HashMap<>();
        result.put("status", status);
        result.put("event_id", eventId);
        result.put("payment_id", paymentId);
        if (reason != null) {
            result.put("reason", reason);
        }
        return result;
    }

    private String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }

    private String firstNonBlank(String... values) {
        if (values == null) {
            return null;
        }
        for (String value : values) {
            String trimmed = trimToNull(value);
            if (trimmed != null) {
                return trimmed;
            }
        }
        return null;
    }

    private void incrementWebhookMetric(PaymentProvider provider, String outcome) {
        Metrics.counter(
            "commerce.webhook.events.total",
            "provider",
            provider.name().toLowerCase(Locale.ROOT),
            "outcome",
            outcome
        ).increment();
    }

    private LocalDate parseLocalDateOrNull(String value, String fieldName) {
        String trimmed = trimToNull(value);
        if (trimmed == null) {
            return null;
        }
        try {
            return LocalDate.parse(trimmed);
        } catch (Exception ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", fieldName + " 날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)");
        }
    }
}
