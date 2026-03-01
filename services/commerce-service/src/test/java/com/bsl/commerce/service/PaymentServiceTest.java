package com.bsl.commerce.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.config.PaymentProperties;
import com.bsl.commerce.repository.OrderRepository;
import com.bsl.commerce.repository.PaymentRepository;
import com.bsl.commerce.service.payment.PaymentGateway;
import com.bsl.commerce.service.payment.PaymentGatewayFactory;
import com.bsl.commerce.service.payment.PaymentProvider;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;

@ExtendWith(MockitoExtension.class)
class PaymentServiceTest {

    @Mock
    private PaymentRepository paymentRepository;

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private OrderService orderService;

    @Mock
    private InventoryService inventoryService;

    @Mock
    private ShipmentService shipmentService;

    @Mock
    private LoyaltyPointService loyaltyPointService;

    @Mock
    private LedgerService ledgerService;

    @Mock
    private PaymentGatewayFactory paymentGatewayFactory;

    @Mock
    private PaymentGateway paymentGateway;

    @Mock
    private PaymentProperties paymentProperties;

    private final ObjectMapper objectMapper = new ObjectMapper();

    private PaymentService newService() {
        return new PaymentService(
            paymentRepository,
            orderRepository,
            orderService,
            inventoryService,
            shipmentService,
            loyaltyPointService,
            ledgerService,
            paymentGatewayFactory,
            paymentProperties,
            objectMapper
        );
    }

    @Test
    void createPaymentReturnsExistingWhenInsertRacesOnIdempotencyKey() {
        PaymentService service = newService();
        stubCreateGateway(PaymentProvider.MOCK, "PROCESSING");

        Map<String, Object> order = Map.of(
            "order_id", 77L,
            "status", "PAYMENT_PENDING",
            "total_amount", 12000,
            "currency", "KRW"
        );
        Map<String, Object> existing = Map.of(
            "payment_id", 501L,
            "order_id", 77L,
            "status", "PROCESSING",
            "amount", 12000,
            "idempotency_key", "race_key"
        );

        when(paymentRepository.findPaymentByIdempotencyKey("race_key")).thenReturn(null, existing);
        when(orderRepository.findOrderById(77L)).thenReturn(order);
        when(
            paymentRepository.insertPayment(
                anyLong(),
                any(),
                any(),
                anyInt(),
                any(),
                any(),
                any(),
                any()
            )
        ).thenThrow(new DuplicateKeyException("duplicate idempotency key"));

        Map<String, Object> result = service.createPayment(77L, 12000, "CARD", "race_key");

        assertThat(result).isEqualTo(existing);
        verify(paymentRepository, never()).insertPaymentEvent(anyLong(), any(), any(), any());
    }

    @Test
    void createPaymentUsesConfiguredProviderCheckoutSessionAndMetadata() {
        PaymentService service = newService();
        stubCreateGateway(PaymentProvider.LOCAL_SIM, "PROCESSING");
        when(paymentGateway.initiatedEventType()).thenReturn("PAYMENT_PROCESSING");
        when(paymentProperties.getDefaultReturnUrl()).thenReturn("http://localhost:5174/payment/result");
        when(paymentProperties.getDefaultWebhookUrl()).thenReturn("http://localhost:8091/api/v1/payments/webhook/{provider}");
        when(paymentProperties.getMockCheckoutBaseUrl()).thenReturn("http://localhost:8090/checkout");
        when(paymentProperties.getSessionTtlSeconds()).thenReturn(1800L);

        Map<String, Object> order = Map.of(
            "order_id", 88L,
            "status", "PAYMENT_PENDING",
            "total_amount", 42000,
            "currency", "KRW"
        );
        Map<String, Object> inserted = Map.of(
            "payment_id", 901L,
            "order_id", 88L,
            "provider", "LOCAL_SIM",
            "status", "PROCESSING",
            "amount", 42000,
            "checkout_session_id", "localsim-901-a1b2c3d4"
        );

        PaymentGateway.CheckoutSession session = new PaymentGateway.CheckoutSession(
            "localsim-901-a1b2c3d4",
            "http://localhost:8090/checkout?session_id=localsim-901-a1b2c3d4",
            Instant.parse("2026-03-01T00:30:00Z")
        );

        when(paymentRepository.findPaymentByIdempotencyKey("idem-901")).thenReturn(null);
        when(orderRepository.findOrderById(88L)).thenReturn(order);
        when(
            paymentRepository.insertPayment(
                eq(88L),
                eq("CARD"),
                eq("PROCESSING"),
                eq(42000),
                eq("KRW"),
                eq("LOCAL_SIM"),
                isNull(),
                eq("idem-901")
            )
        ).thenReturn(901L);
        when(paymentGateway.createCheckoutSession(any())).thenReturn(session);
        when(paymentRepository.findPayment(901L)).thenReturn(inserted);

        Map<String, Object> result = service.createPayment(88L, 42000, "CARD", "idem-901");

        assertThat(result).isEqualTo(inserted);
        verify(paymentRepository).updateCheckoutContext(
            eq(901L),
            eq("localsim-901-a1b2c3d4"),
            eq("http://localhost:5174/payment/result"),
            eq("http://localhost:8091/api/v1/payments/webhook/local_sim"),
            eq("http://localhost:8090/checkout?session_id=localsim-901-a1b2c3d4"),
            eq(Instant.parse("2026-03-01T00:30:00Z"))
        );
        verify(paymentRepository).insertPaymentEvent(eq(901L), eq("PAYMENT_PROCESSING"), isNull(), anyString());
    }

    @Test
    void handleWebhookRejectsInvalidSignatureAndMarksEventFailed() {
        PaymentService service = newService();
        when(paymentProperties.getMockWebhookSecret()).thenReturn("test_secret");

        String rawPayload = "{\"event_id\":\"evt-1\",\"payment_id\":31,\"status\":\"SUCCESS\"}";
        when(
            paymentRepository.insertWebhookEvent(
                eq("MOCK"),
                eq("evt-1"),
                eq(31L),
                eq(false),
                anyString(),
                eq("RECEIVED")
            )
        ).thenReturn(PaymentRepository.WebhookInsertResult.INSERTED);

        assertThatThrownBy(() -> service.handleWebhook("mock", rawPayload, "sha256=bad", "evt-1"))
            .isInstanceOf(ApiException.class)
            .satisfies(error -> {
                ApiException ex = (ApiException) error;
                assertThat(ex.getStatus()).isEqualTo(HttpStatus.UNAUTHORIZED);
                assertThat(ex.getCode()).isEqualTo("invalid_signature");
            });

        verify(paymentRepository).updateWebhookEventStatus("evt-1", false, "FAILED", "invalid_signature");
        verify(paymentRepository, never()).updatePaymentStatus(anyLong(), anyString(), any(), any());
    }

    @Test
    void handleWebhookReturnsDuplicateWithoutApplyingStateTransition() {
        PaymentService service = newService();

        String rawPayload = "{\"event_id\":\"evt-dup\",\"payment_id\":31,\"status\":\"SUCCESS\"}";
        when(
            paymentRepository.insertWebhookEvent(
                eq("MOCK"),
                eq("evt-dup"),
                eq(31L),
                eq(false),
                anyString(),
                eq("RECEIVED")
            )
        ).thenReturn(PaymentRepository.WebhookInsertResult.DUPLICATE);

        Map<String, Object> result = service.handleWebhook("mock", rawPayload, "sha256=deadbeef", "evt-dup");

        assertThat(result.get("status")).isEqualTo("duplicate");
        verify(paymentRepository, never()).updatePaymentStatus(anyLong(), anyString(), any(), any());
        verify(paymentRepository, never()).updateWebhookEventStatus(anyString(), anyBoolean(), anyString(), any());
    }

    @Test
    void handleWebhookCapturesPaymentAndMarksOrderPaid() {
        PaymentService service = newService();
        when(paymentProperties.getMockWebhookSecret()).thenReturn("test_secret");

        String rawPayload = "{\"event_id\":\"evt-ok\",\"payment_id\":31,\"status\":\"SUCCESS\",\"provider_payment_id\":\"pg_31\"}";
        String signature = "sha256=" + hmacSha256Hex("test_secret", rawPayload);

        Map<String, Object> payment = Map.of(
            "payment_id", 31L,
            "order_id", 11L,
            "provider", "MOCK",
            "status", "PROCESSING",
            "amount", 311000,
            "currency", "KRW"
        );

        when(
            paymentRepository.insertWebhookEvent(
                eq("MOCK"),
                eq("evt-ok"),
                eq(31L),
                eq(false),
                anyString(),
                eq("RECEIVED")
            )
        ).thenReturn(PaymentRepository.WebhookInsertResult.INSERTED);
        when(paymentRepository.findPayment(31L)).thenReturn(payment);
        when(orderRepository.findOrderItems(11L)).thenReturn(List.of());
        when(orderRepository.findOrderById(11L)).thenReturn(null);

        Map<String, Object> result = service.handleWebhook("mock", rawPayload, signature, "evt-ok");

        assertThat(result.get("status")).isEqualTo("processed");
        verify(paymentRepository).updatePaymentStatus(31L, "CAPTURED", "pg_31", null);
        verify(paymentRepository).insertPaymentEvent(eq(31L), eq("CAPTURE_SUCCEEDED"), eq("evt-ok"), anyString());
        verify(orderService).markPaid(11L, "31");
        verify(ledgerService).recordPaymentCaptured(31L, 11L, List.of(), "KRW");
        verify(paymentRepository).updateWebhookEventStatus("evt-ok", true, "PROCESSED", null);
    }

    @Test
    void listWebhookEventsForOpsDelegatesRepositoryWithFilters() {
        PaymentService service = newService();
        List<Map<String, Object>> expected = List.of(Map.of("event_id", "evt-x", "process_status", "FAILED"));
        when(paymentRepository.listWebhookEvents(200, "FAILED", "MOCK")).thenReturn(expected);

        List<Map<String, Object>> result = service.listWebhookEventsForOps(999, " FAILED ", " MOCK ");

        assertThat(result).isEqualTo(expected);
        verify(paymentRepository).listWebhookEvents(200, "FAILED", "MOCK");
    }

    @Test
    void manualRetryWebhookEventMarksRetryLifecycle() {
        PaymentService service = newService();
        when(paymentRepository.findWebhookEventByEventId("evt-failed")).thenReturn(
            Map.of(
                "event_id", "evt-failed",
                "provider", "MOCK",
                "payload_json", "{\"event_id\":\"evt-origin\",\"payment_id\":31,\"status\":\"SUCCESS\"}"
            )
        );
        when(
            paymentRepository.insertWebhookEvent(
                eq("MOCK"),
                anyString(),
                eq(31L),
                eq(false),
                anyString(),
                eq("RECEIVED")
            )
        ).thenReturn(PaymentRepository.WebhookInsertResult.INSERTED);
        when(paymentRepository.findPayment(31L)).thenReturn(
            Map.of("payment_id", 31L, "order_id", 11L, "status", "CAPTURED", "provider", "MOCK")
        );

        Map<String, Object> result = service.retryWebhookEvent("evt-failed");

        assertThat(result.get("status")).isEqualTo("processed");
        verify(paymentRepository).markWebhookRetryAttempt("evt-failed", 0, "manual_retry_attempt");
        verify(paymentRepository).markWebhookRetryResolved("evt-failed", "RETRIED", "manual_retry_processed");
    }

    private void stubCreateGateway(PaymentProvider provider, String initiatedStatus) {
        when(paymentProperties.getDefaultProvider()).thenReturn(provider);
        when(paymentGatewayFactory.get(provider)).thenReturn(paymentGateway);
        when(paymentGateway.provider()).thenReturn(provider);
        when(paymentGateway.initiatedStatus()).thenReturn(initiatedStatus);
    }

    private String hmacSha256Hex(String secret, String body) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            byte[] hash = mac.doFinal(body.getBytes(StandardCharsets.UTF_8));
            return java.util.HexFormat.of().formatHex(hash);
        } catch (Exception ex) {
            throw new IllegalStateException(ex);
        }
    }
}
