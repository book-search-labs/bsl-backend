package com.bsl.commerce.config;

import com.bsl.commerce.service.payment.PaymentProvider;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payments")
public class PaymentProperties {
    private PaymentProvider defaultProvider = PaymentProvider.MOCK;
    private String defaultReturnUrl = "http://localhost:5174/payment/result";
    private String defaultWebhookUrl = "http://localhost:8091/api/v1/payments/webhook/mock";
    private String mockCheckoutBaseUrl = "http://localhost:8090/checkout";
    private long sessionTtlSeconds = 1800L;
    private String mockWebhookSecret = "dev_mock_webhook_secret";
    private String localSimWebhookSecret = "dev_local_sim_webhook_secret";
    private double pgFeeRatePercent = 3.0d;
    private double platformFeeRatePercent = 10.0d;
    private boolean webhookRetryEnabled = true;
    private long webhookRetryDelayMs = 30_000L;
    private long webhookRetryInitialDelayMs = 20_000L;
    private int webhookRetryBatchSize = 20;
    private int webhookRetryMaxAttempts = 3;
    private int webhookRetryBackoffSeconds = 30;

    public PaymentProvider getDefaultProvider() {
        return defaultProvider;
    }

    public void setDefaultProvider(PaymentProvider defaultProvider) {
        this.defaultProvider = defaultProvider;
    }

    public String getDefaultReturnUrl() {
        return defaultReturnUrl;
    }

    public void setDefaultReturnUrl(String defaultReturnUrl) {
        this.defaultReturnUrl = defaultReturnUrl;
    }

    public String getDefaultWebhookUrl() {
        return defaultWebhookUrl;
    }

    public void setDefaultWebhookUrl(String defaultWebhookUrl) {
        this.defaultWebhookUrl = defaultWebhookUrl;
    }

    public String getMockCheckoutBaseUrl() {
        return mockCheckoutBaseUrl;
    }

    public void setMockCheckoutBaseUrl(String mockCheckoutBaseUrl) {
        this.mockCheckoutBaseUrl = mockCheckoutBaseUrl;
    }

    public long getSessionTtlSeconds() {
        return sessionTtlSeconds;
    }

    public void setSessionTtlSeconds(long sessionTtlSeconds) {
        this.sessionTtlSeconds = sessionTtlSeconds;
    }

    public String getMockWebhookSecret() {
        return mockWebhookSecret;
    }

    public void setMockWebhookSecret(String mockWebhookSecret) {
        this.mockWebhookSecret = mockWebhookSecret;
    }

    public String getLocalSimWebhookSecret() {
        return localSimWebhookSecret;
    }

    public void setLocalSimWebhookSecret(String localSimWebhookSecret) {
        this.localSimWebhookSecret = localSimWebhookSecret;
    }

    public double getPgFeeRatePercent() {
        return pgFeeRatePercent;
    }

    public void setPgFeeRatePercent(double pgFeeRatePercent) {
        this.pgFeeRatePercent = pgFeeRatePercent;
    }

    public double getPlatformFeeRatePercent() {
        return platformFeeRatePercent;
    }

    public void setPlatformFeeRatePercent(double platformFeeRatePercent) {
        this.platformFeeRatePercent = platformFeeRatePercent;
    }

    public boolean isWebhookRetryEnabled() {
        return webhookRetryEnabled;
    }

    public void setWebhookRetryEnabled(boolean webhookRetryEnabled) {
        this.webhookRetryEnabled = webhookRetryEnabled;
    }

    public long getWebhookRetryDelayMs() {
        return webhookRetryDelayMs;
    }

    public void setWebhookRetryDelayMs(long webhookRetryDelayMs) {
        this.webhookRetryDelayMs = webhookRetryDelayMs;
    }

    public long getWebhookRetryInitialDelayMs() {
        return webhookRetryInitialDelayMs;
    }

    public void setWebhookRetryInitialDelayMs(long webhookRetryInitialDelayMs) {
        this.webhookRetryInitialDelayMs = webhookRetryInitialDelayMs;
    }

    public int getWebhookRetryBatchSize() {
        return webhookRetryBatchSize;
    }

    public void setWebhookRetryBatchSize(int webhookRetryBatchSize) {
        this.webhookRetryBatchSize = webhookRetryBatchSize;
    }

    public int getWebhookRetryMaxAttempts() {
        return webhookRetryMaxAttempts;
    }

    public void setWebhookRetryMaxAttempts(int webhookRetryMaxAttempts) {
        this.webhookRetryMaxAttempts = webhookRetryMaxAttempts;
    }

    public int getWebhookRetryBackoffSeconds() {
        return webhookRetryBackoffSeconds;
    }

    public void setWebhookRetryBackoffSeconds(int webhookRetryBackoffSeconds) {
        this.webhookRetryBackoffSeconds = webhookRetryBackoffSeconds;
    }
}
