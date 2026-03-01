package com.bsl.commerce.service.payment;

import java.time.Instant;

public interface PaymentGateway {
    PaymentProvider provider();

    String initiatedStatus();

    String initiatedEventType();

    CheckoutSession createCheckoutSession(CreateCheckoutSessionRequest request);

    boolean supportsMockComplete();

    MockCompletionDecision completeMock(long paymentId, String result);

    record CreateCheckoutSessionRequest(
        long paymentId,
        long orderId,
        int amount,
        String currency,
        String returnUrl,
        String webhookUrl,
        String checkoutBaseUrl,
        long sessionTtlSeconds
    ) {
    }

    record CheckoutSession(
        String sessionId,
        String checkoutUrl,
        Instant expiresAt
    ) {
    }

    final class MockCompletionDecision {
        private final boolean captured;
        private final String status;
        private final String providerPaymentId;
        private final String failureReason;
        private final String paymentEventType;

        private MockCompletionDecision(
            boolean captured,
            String status,
            String providerPaymentId,
            String failureReason,
            String paymentEventType
        ) {
            this.captured = captured;
            this.status = status;
            this.providerPaymentId = providerPaymentId;
            this.failureReason = failureReason;
            this.paymentEventType = paymentEventType;
        }

        public static MockCompletionDecision captured(String status, String providerPaymentId, String paymentEventType) {
            return new MockCompletionDecision(true, status, providerPaymentId, null, paymentEventType);
        }

        public static MockCompletionDecision failed(String status, String failureReason, String paymentEventType) {
            return new MockCompletionDecision(false, status, null, failureReason, paymentEventType);
        }

        public boolean isCaptured() {
            return captured;
        }

        public String getStatus() {
            return status;
        }

        public String getProviderPaymentId() {
            return providerPaymentId;
        }

        public String getFailureReason() {
            return failureReason;
        }

        public String getPaymentEventType() {
            return paymentEventType;
        }
    }
}
