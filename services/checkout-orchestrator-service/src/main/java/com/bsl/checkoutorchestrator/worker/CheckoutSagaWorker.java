package com.bsl.checkoutorchestrator.worker;

import com.bsl.checkoutorchestrator.config.CheckoutOrchestratorProperties;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "checkout.worker", name = "enabled", havingValue = "true", matchIfMissing = true)
public class CheckoutSagaWorker {
    private final CheckoutSagaExecutor executor;
    private final CheckoutOrchestratorProperties properties;

    public CheckoutSagaWorker(CheckoutSagaExecutor executor, CheckoutOrchestratorProperties properties) {
        this.executor = executor;
        this.properties = properties;
    }

    @Scheduled(fixedDelayString = "${checkout.worker.poll-delay-ms:1000}")
    public void poll() {
        executor.executeDueSteps(properties.getWorker().getBatchSize(), "worker", "worker");
    }
}
