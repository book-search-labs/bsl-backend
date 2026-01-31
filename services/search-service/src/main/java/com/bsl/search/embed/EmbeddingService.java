package com.bsl.search.embed;

import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class EmbeddingService implements EmbeddingProvider {
    private final EmbeddingProperties properties;
    private final EmbeddingGateway embeddingGateway;
    private final ToyEmbedder toyEmbedder;

    public EmbeddingService(EmbeddingProperties properties, EmbeddingGateway embeddingGateway, ToyEmbedder toyEmbedder) {
        this.properties = properties;
        this.embeddingGateway = embeddingGateway;
        this.toyEmbedder = toyEmbedder;
    }

    @Override
    public List<Double> embed(String text, Integer timeBudgetMs) {
        if (properties.getMode() == EmbeddingMode.HTTP) {
            return embeddingGateway.embed(text, timeBudgetMs);
        }
        return toyEmbedder.embed(text);
    }
}
