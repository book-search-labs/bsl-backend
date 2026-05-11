package com.bsl.checkoutorchestrator.observability;

import com.bsl.checkoutorchestrator.domain.CheckoutStepName;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class CheckoutSagaMetrics {
    private final MeterRegistry registry;

    public CheckoutSagaMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    private CheckoutSagaMetrics() {
        this.registry = null;
    }

    public static CheckoutSagaMetrics noop() {
        return new CheckoutSagaMetrics();
    }

    public void started() {
        increment("checkout_saga_started_total");
    }

    public void completed() {
        increment("checkout_saga_completed_total");
    }

    public void failed(CheckoutStepName step, String reason) {
        increment("checkout_saga_failed_total", "step", step.name(), "reason", safe(reason));
    }

    public void unknown(CheckoutStepName step, String reason) {
        increment("checkout_saga_unknown_total", "step", step.name(), "reason", safe(reason));
    }

    public void reconciliation(CheckoutStepName step, String result) {
        increment("checkout_saga_reconciliation_total", "step", step.name(), "result", safe(result));
    }

    public void manualReview(CheckoutStepName step, String reason) {
        increment("checkout_saga_manual_review_total", "step", step.name(), "reason", safe(reason));
    }

    public void pivotManualReview(CheckoutStepName step, String reason) {
        increment("checkout_saga_pivot_manual_review_total", "step", step.name(), "reason", safe(reason));
    }

    public void compensation(CheckoutStepName step, String result) {
        increment("checkout_compensation_total", "step", step.name(), "result", safe(result));
    }

    private void increment(String name, String... tags) {
        if (registry == null) {
            return;
        }
        Counter.builder(name).tags(tags).register(registry).increment();
    }

    private String safe(String value) {
        return value == null || value.isBlank() ? "unknown" : value;
    }
}
