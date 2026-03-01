package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.config.PaymentProperties;
import com.bsl.commerce.repository.PaymentRepository;
import io.micrometer.core.instrument.Metrics;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class WebhookRetryScheduler {
    private static final Logger logger = LoggerFactory.getLogger(WebhookRetryScheduler.class);

    private final PaymentService paymentService;
    private final PaymentRepository paymentRepository;
    private final PaymentProperties paymentProperties;

    public WebhookRetryScheduler(
        PaymentService paymentService,
        PaymentRepository paymentRepository,
        PaymentProperties paymentProperties
    ) {
        this.paymentService = paymentService;
        this.paymentRepository = paymentRepository;
        this.paymentProperties = paymentProperties;
    }

    @Scheduled(
        fixedDelayString = "${payments.webhook-retry-delay-ms:30000}",
        initialDelayString = "${payments.webhook-retry-initial-delay-ms:20000}"
    )
    public void retryFailedWebhookEvents() {
        if (!paymentProperties.isWebhookRetryEnabled()) {
            return;
        }

        int batchSize = Math.max(1, paymentProperties.getWebhookRetryBatchSize());
        int maxAttempts = Math.max(1, paymentProperties.getWebhookRetryMaxAttempts());
        int backoffSeconds = Math.max(0, paymentProperties.getWebhookRetryBackoffSeconds());

        List<Map<String, Object>> candidates = paymentRepository.listRetryableWebhookEvents(batchSize, maxAttempts);
        if (candidates.isEmpty()) {
            return;
        }

        logger.info(
            "payment_webhook_auto_retry_batch size={} max_attempts={} backoff_seconds={}",
            candidates.size(),
            maxAttempts,
            backoffSeconds
        );
        Metrics.counter("commerce.webhook.retry.total", "outcome", "batch").increment();
        Metrics.counter("commerce.webhook.retry.events.total", "outcome", "candidate").increment(candidates.size());

        for (Map<String, Object> event : candidates) {
            String eventId = JdbcUtils.asString(event.get("event_id"));
            Integer retryCount = JdbcUtils.asInt(event.get("retry_count"));
            int attemptBefore = retryCount == null ? 0 : retryCount;
            if (eventId == null || eventId.isBlank()) {
                continue;
            }

            paymentRepository.markWebhookRetryAttempt(eventId, backoffSeconds, "auto_retry_attempt");
            Metrics.counter("commerce.webhook.retry.events.total", "outcome", "attempt").increment();
            try {
                Map<String, Object> result = paymentService.retryWebhookEventForScheduler(eventId);
                String retryStatus = JdbcUtils.asString(result.get("status"));
                if ("processed".equals(retryStatus) || "duplicate".equals(retryStatus) || "ignored".equals(retryStatus)) {
                    paymentRepository.markWebhookRetryResolved(eventId, "RETRIED", "auto_retry_" + retryStatus);
                }
                Metrics.counter(
                    "commerce.webhook.retry.events.total",
                    "outcome",
                    retryStatus == null ? "unknown" : retryStatus
                ).increment();
                logger.info(
                    "payment_webhook_auto_retry_result event_id={} attempt={} status={}",
                    eventId,
                    attemptBefore + 1,
                    retryStatus
                );
            } catch (ApiException ex) {
                Metrics.counter("commerce.webhook.retry.events.total", "outcome", "failed_api").increment();
                logger.warn(
                    "payment_webhook_auto_retry_failed event_id={} attempt={} code={}",
                    eventId,
                    attemptBefore + 1,
                    ex.getCode()
                );
                if (attemptBefore + 1 >= maxAttempts) {
                    paymentRepository.markWebhookRetryResolved(
                        eventId,
                        "FAILED",
                        "auto_retry_exhausted:" + ex.getCode()
                    );
                    Metrics.counter("commerce.webhook.retry.events.total", "outcome", "exhausted").increment();
                }
            } catch (Exception ex) {
                Metrics.counter("commerce.webhook.retry.events.total", "outcome", "failed_internal").increment();
                logger.warn(
                    "payment_webhook_auto_retry_error event_id={} attempt={} message={}",
                    eventId,
                    attemptBefore + 1,
                    ex.getMessage()
                );
                if (attemptBefore + 1 >= maxAttempts) {
                    paymentRepository.markWebhookRetryResolved(
                        eventId,
                        "FAILED",
                        "auto_retry_exhausted:internal_error"
                    );
                    Metrics.counter("commerce.webhook.retry.events.total", "outcome", "exhausted").increment();
                }
            }
        }
    }
}
