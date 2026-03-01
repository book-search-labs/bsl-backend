package com.bsl.commerce.service.payment;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Component;

@Component
public class LocalSimPaymentGateway implements PaymentGateway {
    @Override
    public PaymentProvider provider() {
        return PaymentProvider.LOCAL_SIM;
    }

    @Override
    public String initiatedStatus() {
        return "PROCESSING";
    }

    @Override
    public String initiatedEventType() {
        return "PAYMENT_PROCESSING";
    }

    @Override
    public CheckoutSession createCheckoutSession(CreateCheckoutSessionRequest request) {
        String sessionId = "localsim-" + request.paymentId() + "-" + UUID.randomUUID().toString().substring(0, 8);
        Instant expiresAt = Instant.now().plusSeconds(Math.max(request.sessionTtlSeconds(), 60L));
        String checkoutUrl = request.checkoutBaseUrl()
            + "?session_id=" + urlEncode(sessionId)
            + "&payment_id=" + request.paymentId()
            + "&order_id=" + request.orderId()
            + "&amount=" + request.amount()
            + "&currency=" + urlEncode(request.currency())
            + "&return_url=" + urlEncode(request.returnUrl())
            + "&webhook_url=" + urlEncode(request.webhookUrl())
            + "&provider=LOCAL_SIM";
        return new CheckoutSession(sessionId, checkoutUrl, expiresAt);
    }

    @Override
    public boolean supportsMockComplete() {
        return true;
    }

    @Override
    public MockCompletionDecision completeMock(long paymentId, String result) {
        boolean success = "SUCCESS".equalsIgnoreCase(result);
        if (success) {
            return MockCompletionDecision.captured("CAPTURED", "localsim-" + paymentId, "CAPTURE_SUCCEEDED");
        }
        return MockCompletionDecision.failed("FAILED", "localsim_failed", "CAPTURE_FAILED");
    }

    private String urlEncode(String value) {
        return URLEncoder.encode(value == null ? "" : value, StandardCharsets.UTF_8);
    }
}
