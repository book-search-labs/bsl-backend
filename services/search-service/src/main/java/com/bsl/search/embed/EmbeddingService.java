package com.bsl.search.embed;

import java.util.List;
import org.springframework.stereotype.Component;
import com.bsl.search.resilience.CircuitBreaker;
import com.bsl.search.resilience.SearchResilienceRegistry;

@Component
public class EmbeddingService implements EmbeddingProvider {
    private final EmbeddingProperties properties;
    private final EmbeddingGateway embeddingGateway;
    private final ToyEmbedder toyEmbedder;
    private final EmbeddingCacheService cacheService;
    private final SearchResilienceRegistry resilienceRegistry;

    public EmbeddingService(
        EmbeddingProperties properties,
        EmbeddingGateway embeddingGateway,
        ToyEmbedder toyEmbedder,
        EmbeddingCacheService cacheService,
        SearchResilienceRegistry resilienceRegistry
    ) {
        this.properties = properties;
        this.embeddingGateway = embeddingGateway;
        this.toyEmbedder = toyEmbedder;
        this.cacheService = cacheService;
        this.resilienceRegistry = resilienceRegistry;
    }

    @Override
    public List<Double> embed(String text, Integer timeBudgetMs) {
        return embed(text, timeBudgetMs, null, null);
    }

    @Override
    public List<Double> embed(String text, Integer timeBudgetMs, String traceId, String requestId) {
        if (cacheService.isEnabled()) {
            return cacheService.get(text)
                .orElseGet(() -> fetchAndCache(text, timeBudgetMs, traceId, requestId));
        }
        return fetch(text, timeBudgetMs, traceId, requestId);
    }

    private List<Double> fetchAndCache(String text, Integer timeBudgetMs, String traceId, String requestId) {
        List<Double> vector = fetch(text, timeBudgetMs, traceId, requestId);
        cacheService.put(text, vector);
        return vector;
    }

    private List<Double> fetch(String text, Integer timeBudgetMs, String traceId, String requestId) {
        if (properties.getMode() == EmbeddingMode.HTTP) {
            CircuitBreaker breaker = resilienceRegistry.getEmbedBreaker();
            if (!breaker.allowRequest()) {
                throw new EmbeddingUnavailableException("embed_circuit_open");
            }
            try {
                List<Double> vector = embeddingGateway.embed(text, timeBudgetMs, traceId, requestId);
                breaker.recordSuccess();
                return vector;
            } catch (EmbeddingUnavailableException ex) {
                breaker.recordFailure();
                throw ex;
            }
        }
        return toyEmbedder.embed(text);
    }
}
