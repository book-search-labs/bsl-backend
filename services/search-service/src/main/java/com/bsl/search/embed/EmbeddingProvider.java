package com.bsl.search.embed;

import java.util.List;

public interface EmbeddingProvider {
    List<Double> embed(String text, Integer timeBudgetMs);

    default List<Double> embed(String text, Integer timeBudgetMs, String traceId, String requestId) {
        return embed(text, timeBudgetMs);
    }
}
