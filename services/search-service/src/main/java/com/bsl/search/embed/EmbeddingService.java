package com.bsl.search.embed;

import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class EmbeddingService implements EmbeddingProvider {
    private final EmbeddingProperties properties;
    private final EmbeddingGateway embeddingGateway;
    private final ToyEmbedder toyEmbedder;
    private final EmbeddingCacheService cacheService;

    public EmbeddingService(
        EmbeddingProperties properties,
        EmbeddingGateway embeddingGateway,
        ToyEmbedder toyEmbedder,
        EmbeddingCacheService cacheService
    ) {
        this.properties = properties;
        this.embeddingGateway = embeddingGateway;
        this.toyEmbedder = toyEmbedder;
        this.cacheService = cacheService;
    }

    @Override
    public List<Double> embed(String text, Integer timeBudgetMs) {
        if (cacheService.isEnabled()) {
            return cacheService.get(text)
                .orElseGet(() -> fetchAndCache(text, timeBudgetMs));
        }
        return fetch(text, timeBudgetMs);
    }

    private List<Double> fetchAndCache(String text, Integer timeBudgetMs) {
        List<Double> vector = fetch(text, timeBudgetMs);
        cacheService.put(text, vector);
        return vector;
    }

    private List<Double> fetch(String text, Integer timeBudgetMs) {
        if (properties.getMode() == EmbeddingMode.HTTP) {
            return embeddingGateway.embed(text, timeBudgetMs);
        }
        return toyEmbedder.embed(text);
    }
}
