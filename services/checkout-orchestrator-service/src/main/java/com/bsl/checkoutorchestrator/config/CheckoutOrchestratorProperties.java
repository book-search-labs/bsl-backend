package com.bsl.checkoutorchestrator.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public class CheckoutOrchestratorProperties {
    private final Worker worker = new Worker();
    private final Downstream downstream = new Downstream();

    public Worker getWorker() {
        return worker;
    }

    public Downstream getDownstream() {
        return downstream;
    }

    public static class Worker {
        private boolean enabled = true;
        private long pollDelayMs = 1_000;
        private int batchSize = 10;
        private long retryDelayMs = 2_000;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public long getPollDelayMs() {
            return pollDelayMs;
        }

        public void setPollDelayMs(long pollDelayMs) {
            this.pollDelayMs = pollDelayMs;
        }

        public int getBatchSize() {
            return batchSize;
        }

        public void setBatchSize(int batchSize) {
            this.batchSize = batchSize;
        }

        public long getRetryDelayMs() {
            return retryDelayMs;
        }

        public void setRetryDelayMs(long retryDelayMs) {
            this.retryDelayMs = retryDelayMs;
        }
    }

    public static class Downstream {
        private final Service orderService = new Service("http://localhost:8092", 700);
        private final Service paymentService = new Service("http://localhost:8093", 700);
        private final Service inventoryService = new Service("http://localhost:8094", 700);
        private final Service shipmentService = new Service("http://localhost:8097", 700);

        public Service getOrderService() {
            return orderService;
        }

        public Service getPaymentService() {
            return paymentService;
        }

        public Service getInventoryService() {
            return inventoryService;
        }

        public Service getShipmentService() {
            return shipmentService;
        }
    }

    public static class Service {
        private String baseUrl;
        private int timeoutMs;

        public Service() {
        }

        public Service(String baseUrl, int timeoutMs) {
            this.baseUrl = baseUrl;
            this.timeoutMs = timeoutMs;
        }

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public int getTimeoutMs() {
            return timeoutMs;
        }

        public void setTimeoutMs(int timeoutMs) {
            this.timeoutMs = timeoutMs;
        }
    }
}

