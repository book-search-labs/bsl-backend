package com.bsl.refund.api;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class HealthControllerTest {
    @Test
    void healthReturnsOk() {
        assertThat(new HealthController().health("trace", "request"))
            .containsEntry("service", "refund-service")
            .containsEntry("status", "ok");
    }
}
