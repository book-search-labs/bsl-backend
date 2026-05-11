package com.bsl.bff.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "bff.downstream")
public class DownstreamProperties {
    private ServiceProperties queryService = new ServiceProperties();
    private ServiceProperties searchService = new ServiceProperties();
    private ServiceProperties autocompleteService = new ServiceProperties();
    private ServiceProperties indexWriterService = new ServiceProperties();
    private ServiceProperties misService = new ServiceProperties();
    private ServiceProperties commerceService = new ServiceProperties();
    private ServiceProperties checkoutOrchestratorService = new ServiceProperties();
    private ServiceProperties refundService = new ServiceProperties();

    public ServiceProperties getQueryService() {
        return queryService;
    }

    public void setQueryService(ServiceProperties queryService) {
        this.queryService = queryService;
    }

    public ServiceProperties getSearchService() {
        return searchService;
    }

    public void setSearchService(ServiceProperties searchService) {
        this.searchService = searchService;
    }

    public ServiceProperties getAutocompleteService() {
        return autocompleteService;
    }

    public void setAutocompleteService(ServiceProperties autocompleteService) {
        this.autocompleteService = autocompleteService;
    }

    public ServiceProperties getIndexWriterService() {
        return indexWriterService;
    }

    public void setIndexWriterService(ServiceProperties indexWriterService) {
        this.indexWriterService = indexWriterService;
    }

    public ServiceProperties getMisService() {
        return misService;
    }

    public void setMisService(ServiceProperties misService) {
        this.misService = misService;
    }

    public ServiceProperties getCommerceService() {
        return commerceService;
    }

    public void setCommerceService(ServiceProperties commerceService) {
        this.commerceService = commerceService;
    }

    public ServiceProperties getCheckoutOrchestratorService() {
        return checkoutOrchestratorService;
    }

    public void setCheckoutOrchestratorService(ServiceProperties checkoutOrchestratorService) {
        this.checkoutOrchestratorService = checkoutOrchestratorService;
    }

    public ServiceProperties getRefundService() {
        return refundService;
    }

    public void setRefundService(ServiceProperties refundService) {
        this.refundService = refundService;
    }

    public static class ServiceProperties {
        private String baseUrl;
        private int timeoutMs = 300;

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
