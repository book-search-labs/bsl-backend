package com.bsl.commerce.service;

import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.config.PaymentProperties;
import com.bsl.commerce.repository.PaymentRepository;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;

@ExtendWith(MockitoExtension.class)
class WebhookRetrySchedulerTest {

    @Mock
    private PaymentService paymentService;

    @Mock
    private PaymentRepository paymentRepository;

    private PaymentProperties paymentProperties;
    private WebhookRetryScheduler scheduler;

    @BeforeEach
    void setUp() {
        paymentProperties = new PaymentProperties();
        paymentProperties.setWebhookRetryEnabled(true);
        paymentProperties.setWebhookRetryBatchSize(20);
        paymentProperties.setWebhookRetryMaxAttempts(3);
        paymentProperties.setWebhookRetryBackoffSeconds(30);
        scheduler = new WebhookRetryScheduler(paymentService, paymentRepository, paymentProperties);
    }

    @Test
    void skipsWhenWebhookRetryDisabled() {
        paymentProperties.setWebhookRetryEnabled(false);

        scheduler.retryFailedWebhookEvents();

        verify(paymentRepository, never()).listRetryableWebhookEvents(20, 3);
        verify(paymentService, never()).retryWebhookEventForScheduler("evt-1");
    }

    @Test
    void retriesCandidateAndMarksRetriedOnProcessed() {
        when(paymentRepository.listRetryableWebhookEvents(20, 3)).thenReturn(
            List.of(Map.of("event_id", "evt-1", "retry_count", 0))
        );
        when(paymentService.retryWebhookEventForScheduler("evt-1")).thenReturn(Map.of("status", "processed"));

        scheduler.retryFailedWebhookEvents();

        verify(paymentRepository).markWebhookRetryAttempt("evt-1", 30, "auto_retry_attempt");
        verify(paymentService).retryWebhookEventForScheduler("evt-1");
        verify(paymentRepository).markWebhookRetryResolved("evt-1", "RETRIED", "auto_retry_processed");
    }

    @Test
    void marksExhaustedWhenRetryFailsAtMaxAttempt() {
        paymentProperties.setWebhookRetryMaxAttempts(2);
        when(paymentRepository.listRetryableWebhookEvents(20, 2)).thenReturn(
            List.of(Map.of("event_id", "evt-2", "retry_count", 1))
        );
        when(paymentService.retryWebhookEventForScheduler("evt-2")).thenThrow(
            new ApiException(HttpStatus.CONFLICT, "invalid_state", "invalid transition")
        );

        scheduler.retryFailedWebhookEvents();

        verify(paymentRepository).markWebhookRetryAttempt("evt-2", 30, "auto_retry_attempt");
        verify(paymentRepository).markWebhookRetryResolved("evt-2", "FAILED", "auto_retry_exhausted:invalid_state");
    }
}
