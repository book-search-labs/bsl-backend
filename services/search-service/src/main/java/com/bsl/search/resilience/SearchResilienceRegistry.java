package com.bsl.search.resilience;

import org.springframework.stereotype.Component;

@Component
public class SearchResilienceRegistry {
    private final SearchResilienceProperties properties;
    private final CircuitBreaker embedBreaker;
    private final CircuitBreaker vectorBreaker;
    private final CircuitBreaker rerankBreaker;

    public SearchResilienceRegistry(SearchResilienceProperties properties) {
        this.properties = properties;
        this.embedBreaker = new CircuitBreaker(properties.getEmbedFailureThreshold(), properties.getEmbedOpenMs());
        this.vectorBreaker = new CircuitBreaker(properties.getVectorFailureThreshold(), properties.getVectorOpenMs());
        this.rerankBreaker = new CircuitBreaker(properties.getRerankFailureThreshold(), properties.getRerankOpenMs());
    }

    public CircuitBreaker getEmbedBreaker() {
        return embedBreaker;
    }

    public CircuitBreaker getVectorBreaker() {
        return vectorBreaker;
    }

    public CircuitBreaker getRerankBreaker() {
        return rerankBreaker;
    }

    public SearchResilienceProperties getProperties() {
        return properties;
    }
}
