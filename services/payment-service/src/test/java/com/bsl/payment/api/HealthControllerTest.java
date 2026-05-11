package com.bsl.payment.api;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class HealthControllerTest {
    @Test
    void healthReturnsOk() {
        assertThat(new HealthController().health("trace", "request"))
            .containsEntry("service", "payment-service")
            .containsEntry("status", "ok");
    }
}
