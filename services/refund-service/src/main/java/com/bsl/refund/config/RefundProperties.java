package com.bsl.refund.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "refund.downstream")
public class RefundProperties {
    private ServiceProperties paymentService = new ServiceProperties();
    private ServiceProperties inventoryService = new ServiceProperties();

    public ServiceProperties getPaymentService() {
        return paymentService;
    }

    public void setPaymentService(ServiceProperties paymentService) {
        this.paymentService = paymentService;
    }

    public ServiceProperties getInventoryService() {
        return inventoryService;
    }

    public void setInventoryService(ServiceProperties inventoryService) {
        this.inventoryService = inventoryService;
    }

    public static class ServiceProperties {
        private String baseUrl;
        private int timeoutMs = 700;

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
