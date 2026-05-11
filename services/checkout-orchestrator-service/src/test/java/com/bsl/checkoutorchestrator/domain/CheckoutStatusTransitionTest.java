package com.bsl.checkoutorchestrator.domain;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class CheckoutStatusTransitionTest {
    @Test
    void stepTransitionsIncludeUnknownReconciliationPath() {
        assertThat(CheckoutStepStatus.canTransition(null, CheckoutStepStatus.READY)).isTrue();
        assertThat(CheckoutStepStatus.canTransition(CheckoutStepStatus.READY, CheckoutStepStatus.PROCESSING)).isTrue();
        assertThat(CheckoutStepStatus.canTransition(CheckoutStepStatus.PROCESSING, CheckoutStepStatus.UNKNOWN)).isTrue();
        assertThat(CheckoutStepStatus.canTransition(CheckoutStepStatus.UNKNOWN, CheckoutStepStatus.SUCCEEDED)).isTrue();
        assertThat(CheckoutStepStatus.canTransition(CheckoutStepStatus.UNKNOWN, CheckoutStepStatus.FAILED_RETRYING)).isTrue();
        assertThat(CheckoutStepStatus.canTransition(CheckoutStepStatus.UNKNOWN, CheckoutStepStatus.MANUAL_REVIEW_REQUIRED)).isTrue();
        assertThat(CheckoutStepStatus.canTransition(CheckoutStepStatus.SUCCEEDED, CheckoutStepStatus.READY)).isFalse();
    }

    @Test
    void sagaTransitionsSupportForwardRetryAndCancel() {
        assertThat(CheckoutSagaStatus.canTransition(null, CheckoutSagaStatus.PENDING)).isTrue();
        assertThat(CheckoutSagaStatus.canTransition(CheckoutSagaStatus.PENDING, CheckoutSagaStatus.PROCESSING)).isTrue();
        assertThat(CheckoutSagaStatus.canTransition(CheckoutSagaStatus.PROCESSING, CheckoutSagaStatus.FAILED_RETRYING)).isTrue();
        assertThat(CheckoutSagaStatus.canTransition(CheckoutSagaStatus.FAILED_RETRYING, CheckoutSagaStatus.PROCESSING)).isTrue();
        assertThat(CheckoutSagaStatus.canTransition(CheckoutSagaStatus.PROCESSING, CheckoutSagaStatus.CANCELLING)).isTrue();
        assertThat(CheckoutSagaStatus.canTransition(CheckoutSagaStatus.CANCELLING, CheckoutSagaStatus.CANCELLED)).isTrue();
        assertThat(CheckoutSagaStatus.canTransition(CheckoutSagaStatus.CANCELLED, CheckoutSagaStatus.PROCESSING)).isFalse();
    }
}
