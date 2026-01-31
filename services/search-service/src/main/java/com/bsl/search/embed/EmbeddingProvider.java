package com.bsl.search.embed;

import java.util.List;

public interface EmbeddingProvider {
    List<Double> embed(String text, Integer timeBudgetMs);
}
