package com.bsl.bff.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "bff.downstream")
public class DownstreamProperties {
    private ServiceProperties queryService = new ServiceProperties();
    private ServiceProperties searchService = new ServiceProperties();
    private ServiceProperties autocompleteService = new ServiceProperties();
    private ServiceProperties indexWriterService = new ServiceProperties();

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
